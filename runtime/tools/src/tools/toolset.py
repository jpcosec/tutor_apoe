"""Las tools de negocio como tools de Pydantic AI (docs/reemplazos-pydantic-ai-y-separacion-cliente.md §1.1).

El agente las llama directamente: Pydantic AI valida los argumentos contra `Args` y le pide al
modelo que corrija si no calzan, y aplica el plazo de cada tool. La ejecución es la misma de
siempre (la tool semántica sobre sus primitivas); cada llamada se entrega a `record` para que
quede en la traza del turno.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, MutableMapping
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel
from pydantic_ai import RunContext
from pydantic_ai import Tool as AgentTool
from pydantic_ai.toolsets import FunctionToolset

from ontology import new_id
from tools.contract import IdentityCheck, Tool, ToolContext, ToolError, ToolOutcome
from tools.idempotency import UNCERTAIN, IdempotencyPort, idempotency_key

log = logging.getLogger(__name__)


class IdentityPort(Protocol):
    """`identity_links` de 02 (§6.2): compara lo afirmado con lo cargado; nunca lanza."""

    def verify(self, subject_key: str, kind: str, claimed: str) -> IdentityCheck: ...


#: Recibe cada llamada ya ejecutada y cuándo empezó.
Record = Callable[[ToolOutcome, datetime], None]


def execute(tool: Tool, context: ToolContext, args: BaseModel) -> ToolOutcome:
    """Corre la tool con su propio id de llamada; con `idempotency_key`, a lo más una vez por clave
    y sujeto (03 I7): la clave se reserva antes del efecto en el puerto `idempotency`.

    Es el núcleo común de `ToolRunner` y de `business_toolset`, que son las entradas públicas."""
    call_id = context.call_id or new_id()
    scoped = context.model_copy(update={"call_id": call_id, "writes": type(tool).writes})
    identity = check_identity(tool, context, args)
    if identity is not None and not identity.verified:
        return ToolOutcome(
            call_id=call_id,
            name=tool.name,
            status="rejected",
            error_class="identity_not_verified",
            identity=identity,
        )
    outcome = _once(tool, scoped, args)
    return outcome if identity is None else outcome.model_copy(update={"identity": identity})


def check_identity(tool: Tool, context: ToolContext, args: BaseModel) -> IdentityCheck | None:
    """03 I5: el valor que manda el modelo solo se compara con el vínculo verificado del sujeto;
    sin puerto de identidad no hay con qué comparar y la tool no corre. None si no lo exige."""
    required = type(tool).requires_identity
    if required is None:
        return None
    port: IdentityPort | None = context.ports.get("identity_links")
    claimed = getattr(args, required.arg, None)
    if port is None or claimed is None:
        return IdentityCheck(provided=port is not None and claimed is not None, verified=False)
    found = port.verify(context.session_id, required.kind, str(claimed))
    return IdentityCheck(provided=found.provided, verified=found.verified)


def _once(tool: Tool, context: ToolContext, args: BaseModel) -> ToolOutcome:
    """Con `idempotency_key`, a lo más una vez por clave (03 I7, D15).

    Tool local: reserva, efecto y resultado van en la misma unidad de trabajo; cualquier error
    revierte las tres cosas y la clave queda libre. Tool externa: el efecto no se puede revertir,
    así que la reserva se confirma antes; un error conocido la libera y uno incierto la deja
    `pending` (nadie vuelve a ejecutar el efecto hasta reconciliarla).
    """
    port: IdempotencyPort | None = context.ports.get("idempotency")
    kind = type(tool)
    turn = context.turn_id if kind.idempotency_scope == "turn" else None
    key = idempotency_key(kind.idempotency_key, args, turn)
    if port is None or key is None:
        return _run(tool, context, args)
    reservation = _Reservation(port, tool.name, key, context.session_id, context.call_id or new_id())
    if kind.kind != "external" and "work" in context.ports:
        return _run(tool, context, args, reservation)
    early = reservation.enter()
    if early is not None:
        return early
    outcome = _run(tool, context, args)
    if outcome.status == "ok":
        reservation.complete(outcome)
    elif outcome.error_class not in UNCERTAIN:
        port.release(tool.name, key, context.session_id, reservation.call_id)
    return outcome


@dataclass(frozen=True)
class _Reservation:
    port: IdempotencyPort
    name: str
    key: str
    subject: str
    call_id: str

    def enter(self) -> ToolOutcome | None:
        """None si esta llamada tiene la clave; si no, lo que se responde sin ejecutar."""
        held = self.port.reserve(self.name, self.key, self.subject, self.call_id)
        if held.state == "done" and held.outcome is not None:
            return ToolOutcome.model_validate(held.outcome).model_copy(update={"deduplicated": True})
        if held.state != "owned":
            return ToolOutcome(
                call_id=self.call_id, name=self.name, status="error", error_class="in_progress"
            )
        return None

    def complete(self, outcome: ToolOutcome) -> None:
        self.port.complete(self.name, self.key, self.subject, self.call_id, outcome.model_dump(mode="json"))


def _run(
    tool: Tool, context: ToolContext, args: BaseModel, reservation: _Reservation | None = None
) -> ToolOutcome:
    """La tool dentro de una unidad de trabajo (03 I6): si falla, sus escrituras se revierten.
    Un `ToolError` es un resultado, no una excepción; cualquier otra, un defecto."""
    call_id = context.call_id or new_id()
    started = time.perf_counter()
    try:
        with _unit(context):
            early = reservation.enter() if reservation else None
            if early is not None:
                return early
            result = tool.execute(context, args)
            outcome = ToolOutcome(call_id=call_id, name=tool.name, status="ok", result=result)
            if reservation:
                reservation.complete(outcome)
    except ToolError as error:
        outcome = ToolOutcome(
            call_id=call_id,
            name=tool.name,
            status="error",
            error_class=error.error_class,
            message_for_user=error.message_for_user,
            retryable=error.retryable,
        )
    except Exception:
        log.exception("tool %s: defecto", tool.name)
        outcome = ToolOutcome(call_id=call_id, name=tool.name, status="error", error_class="defect")
    return outcome.model_copy(update={"latency_ms": int((time.perf_counter() - started) * 1000)})


class WorkPort(Protocol):
    """`work` de 02: una transacción para todas las escrituras de la llamada."""

    def unit_of_work(self) -> AbstractContextManager[None]: ...


def _unit(context: ToolContext) -> AbstractContextManager[None]:
    work: WorkPort | None = context.ports.get("work")
    return work.unit_of_work() if work is not None else nullcontext()


#: Resultado de cada llamada ya hecha en el turno, por tool y argumentos (`call_key`).
TurnMemo = MutableMapping[str, dict[str, object]]


def business_toolset(
    tools: list[Tool],
    context: Callable[[], ToolContext],
    record: Record,
    memo: TurnMemo | None = None,
) -> FunctionToolset[None]:
    """Un toolset con cada tool habilitada; `context` da el `ToolContext` del turno en curso.

    Cada tool es `sequential`: las de un turno escriben el mismo sujeto (leer-modificar-escribir)
    y "la última tool" depende del orden; llamadas paralelas del modelo corren una tras otra.

    `memo` es la memoria del turno: la misma tool con los mismos argumentos no se ejecuta dos
    veces en un turno (06 decide puede correr al orquestador más de una vez, B3); la repetición
    devuelve el resultado anterior sin anotarlo de nuevo. Un error reintentable no se memoriza.
    """
    return FunctionToolset([_agent_tool(tool, context, record, memo) for tool in tools])


def call_key(name: str, args: BaseModel) -> str:
    """La identidad de una llamada dentro de un turno: tool y argumentos canónicos."""
    return f"{name}:{json.dumps(args.model_dump(mode='json'), sort_keys=True, ensure_ascii=False)}"


def _agent_tool(
    tool: Tool, context: Callable[[], ToolContext], record: Record, memo: TurnMemo | None
) -> AgentTool[None]:
    kind = type(tool)

    def run(ctx: RunContext[None], args: BaseModel) -> dict[str, object]:
        key = call_key(kind.name, args)
        if memo is not None and key in memo:
            return memo[key]
        opened = datetime.now(UTC)
        outcome = execute(tool, context(), args)
        record(outcome, opened)
        result = outcome.for_model()
        if memo is not None and not outcome.retryable:
            memo[key] = result
        return result

    run.__annotations__["args"] = kind.Args  # el esquema que ve el modelo es el `Args` de la tool

    return AgentTool(
        run,
        name=kind.name,
        description=kind.description,
        takes_ctx=True,
        timeout=kind.timeout_seconds,
        sequential=True,
    )
