from __future__ import annotations

import time
from datetime import datetime
from typing import ClassVar

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import RetryPromptPart

from llm import ScriptedModel, ScriptedStep
from tools import (
    Conflict,
    EventSpec,
    NotFound,
    ProviderError,
    Tool,
    ToolCall,
    ToolCatalog,
    ToolContext,
    ToolError,
    ToolResult,
    ToolRunner,
    business_toolset,
    event_tool,
)


class Args(BaseModel):
    n: int


class Doble(Tool):
    name: ClassVar[str] = "doble"
    description: ClassVar[str] = "Duplica."
    Args: ClassVar[type[BaseModel]] = Args
    timeout_seconds: ClassVar[float] = 0.2

    def execute(self, context: ToolContext, args: BaseModel) -> ToolResult:
        n = Args.model_validate(args.model_dump()).n
        if n == 0:
            raise ToolError("not_found")
        if n < 0:
            time.sleep(1)
        if n == 13:
            raise RuntimeError("defecto")
        if n == 500:
            raise ProviderError("El proveedor no responde; vuelvo a intentar en un rato.")
        if n == 404:
            raise NotFound("No encontré esa factura.")
        if n == 409:
            raise Conflict("Esa factura ya está pagada.")
        return ToolResult(data={"doble": n * 2})


def run(arguments: dict[str, object], name: str = "doble") -> dict[str, object]:
    runner = ToolRunner(ToolCatalog([Doble()]))
    return runner.run(
        ToolCall(call_id="c", name=name, arguments=arguments), ToolContext(session_id="s", turn_id="t")
    ).for_model()


@pytest.mark.parametrize(
    ("arguments", "name", "status", "error"),
    [
        ({"n": 2}, "doble", "ok", None),
        ({"n": "x"}, "doble", "rejected", None),
        ({"n": 0}, "doble", "error", "not_found"),
        ({"n": 13}, "doble", "error", "defect"),
        ({}, "no_existe", "unknown", None),
    ],
)
def test_estados_del_runner(arguments: dict[str, object], name: str, status: str, error: str | None) -> None:
    outcome = run(arguments, name)

    assert outcome["status"] == status
    assert outcome.get("error") == error


def test_el_plazo_de_la_tool_lo_aplica_pydantic_ai() -> None:
    """Con plazo vencido el modelo recibe el aviso y la llamada no se anota (docs/reemplazos §1.1)."""
    recorded: list[str] = []
    context = ToolContext(session_id="s", turn_id="t")
    toolset = business_toolset([Doble()], lambda: context, lambda outcome, _: recorded.append(outcome.status))
    call = ScriptedStep(text="", tool_calls=[{"name": "doble", "arguments": {"n": -1}}])

    result = Agent(
        ScriptedModel([call, ScriptedStep(text="listo")]).model, deps_type=type(None), toolsets=[toolset]
    ).run_sync("x")

    parts = [p for m in result.all_messages() for p in getattr(m, "parts", [])]
    retries = [p for p in parts if isinstance(p, RetryPromptPart)]
    assert (result.output, recorded) == ("listo", [])
    assert "Timed out" in str(retries[0].content)


def test_las_tools_de_un_turno_no_corren_en_paralelo() -> None:
    """Escriben el mismo sujeto: pydantic-ai las ejecuta como barreras, una tras otra."""
    context = ToolContext(session_id="s", turn_id="t")
    toolset = business_toolset([Doble()], lambda: context, lambda outcome, _: None)

    assert all(tool.sequential for tool in toolset.tools.values())


def test_catalogo_rechaza_repetidas() -> None:
    with pytest.raises(ValueError, match="repetidas"):
        ToolCatalog([Doble(), Doble()])


REGISTRAR = EventSpec(
    name="registrar_evento", description="d", kinds=["derivacion_ejecutiva", "promesa_pago"]
)


def test_una_tool_de_evento_usa_la_primitiva_y_cierra_los_tipos() -> None:
    class Events:
        def __init__(self) -> None:
            self.saved: list[tuple[str, str, dict[str, object], datetime | None]] = []

        def add_event(
            self,
            session_id: str,
            kind: str,
            payload: dict[str, object],
            due_at: datetime | None,
            opened_by: str | None = None,
        ) -> int:
            self.saved.append((session_id, kind, payload, due_at))
            return len(self.saved)

        def set_event_status(self, event_id: int, status: str) -> None: ...

    events = Events()
    tool = event_tool(REGISTRAR)
    runner = ToolRunner(ToolCatalog([tool]))
    context = ToolContext(session_id="s-1", turn_id="t", ports={"subject_events": events})

    ok = runner.run(
        ToolCall(
            call_id="c",
            name="registrar_evento",
            arguments={"kind": "derivacion_ejecutiva", "payload": {"motivo": "descuento"}},
        ),
        context,
    )
    invented = ToolCall(call_id="c", name="registrar_evento", arguments={"kind": "regalo"})
    bad = runner.run(invented, context)

    schema = type(tool).declaration().parameters
    assert schema["properties"]["kind"]["enum"] == ["derivacion_ejecutiva", "promesa_pago"]  # pyright: ignore[reportIndexIssue, reportArgumentType, reportCallIssue]
    assert ok.status == "ok"
    assert ok.result is not None
    assert ok.result.audit["primitives"] == [
        {"primitive": "subject_events.create", "target": "derivacion_ejecutiva", "status": "ok"}
    ]
    assert events.saved == [("s-1", "derivacion_ejecutiva", {"motivo": "descuento"}, None)]
    assert bad.status == "rejected"
    assert events.saved[1:] == []


@pytest.mark.parametrize(
    ("n", "error", "retryable", "message"),
    [
        (500, "provider", True, "El proveedor no responde; vuelvo a intentar en un rato."),
        (404, "not_found", False, "No encontré esa factura."),
        (409, "conflict", False, "Esa factura ya está pagada."),
        (0, "not_found", False, None),
    ],
)
def test_un_error_tipado_llega_al_modelo_con_su_mensaje(
    n: int, error: str, retryable: bool, message: str | None
) -> None:
    outcome = run({"n": n})

    assert (outcome["status"], outcome["error"]) == ("error", error)
    assert (outcome["retryable"], outcome["message_for_user"]) == (retryable, message)


def test_en_un_turno_la_misma_llamada_no_se_ejecuta_dos_veces() -> None:
    """06 decide puede correr al orquestador dos veces en un turno (B3): la memoria del turno
    devuelve el resultado anterior sin volver a ejecutar ni anotar la tool."""
    recorded: list[dict[str, object]] = []
    memo: dict[str, dict[str, object]] = {}
    context = ToolContext(session_id="s", turn_id="t")

    def corrida(*calls: dict[str, object]) -> None:
        toolset = business_toolset(
            [Doble()], lambda: context, lambda outcome, _: recorded.append(outcome.for_model()), memo
        )
        steps = [ScriptedStep(text="", tool_calls=[{"name": "doble", "arguments": a}]) for a in calls]
        Agent(
            ScriptedModel([*steps, ScriptedStep(text="listo")]).model,
            deps_type=type(None),
            toolsets=[toolset],
        ).run_sync("x")

    corrida({"n": 2}, {"n": 0})  # primer salto: una que funciona y una que no encuentra
    corrida({"n": 2}, {"n": 0}, {"n": 3})  # segundo salto: repite las dos y agrega una nueva

    assert [r.get("doble", r.get("error")) for r in recorded] == [4, "not_found", 6]


def test_un_error_reintentable_no_queda_en_la_memoria_del_turno() -> None:
    recorded: list[str] = []
    memo: dict[str, dict[str, object]] = {}
    context = ToolContext(session_id="s", turn_id="t")
    toolset = business_toolset(
        [Doble()], lambda: context, lambda outcome, _: recorded.append(outcome.status), memo
    )
    call = ScriptedStep(text="", tool_calls=[{"name": "doble", "arguments": {"n": 500}}])

    Agent(
        ScriptedModel([call, call, ScriptedStep(text="listo")]).model,
        deps_type=type(None),
        toolsets=[toolset],
    ).run_sync("x")

    assert recorded == ["error", "error"]  # el proveedor puede volver: se reintenta
    assert memo == {}
