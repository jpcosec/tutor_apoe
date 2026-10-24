"""03 I7, D15: con `idempotency_key`, el efecto ocurre a lo más una vez por clave y sujeto."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import ClassVar, Literal

from pydantic import BaseModel

from tools import ToolContext, ToolError, ToolResult
from tools.contract import Tool
from tools.idempotency import idempotency_key
from tools.toolset import execute


@dataclass(frozen=True)
class Held:
    state: Literal["owned", "done", "pending"]
    call_id: str
    outcome: dict[str, object] | None = None


@dataclass
class MemoryPort:
    """La restricción única de 02, en memoria: el candado hace de índice único."""

    rows: dict[tuple[str, str, str], Held] = field(default_factory=dict[tuple[str, str, str], Held])
    lock: threading.Lock = field(default_factory=threading.Lock)

    def reserve(self, name: str, key: str, subject: str, call_id: str) -> Held:
        with self.lock:
            held = self.rows.setdefault((name, key, subject), Held("pending", call_id))
            return Held("owned", call_id) if held.call_id == call_id and held.state == "pending" else held

    def complete(self, name: str, key: str, subject: str, call_id: str, outcome: dict[str, object]) -> None:
        self.rows[(name, key, subject)] = Held("done", call_id, outcome)

    def release(self, name: str, key: str, subject: str, call_id: str) -> None:
        if self.rows.get((name, key, subject), Held("done", "")).call_id == call_id:
            del self.rows[(name, key, subject)]


class Args(BaseModel):
    message_sid: str
    nota: str | None = None


class Registrar(Tool):
    name: ClassVar[str] = "registrar"
    description: ClassVar[str] = "Registra un aviso."
    Args: ClassVar[type[BaseModel]] = Args
    kind: ClassVar[Literal["read", "write", "external"]] = "write"
    idempotency_key: ClassVar[tuple[str, ...]] = ("message_sid",)

    def __init__(self, fail: Exception | None = None) -> None:
        self.effects, self.fail = 0, fail

    def execute(self, context: ToolContext, args: BaseModel) -> ToolResult:
        self.effects += 1
        if self.fail is not None:
            raise self.fail
        return ToolResult(data={"ok": True})


def context(port: MemoryPort, subject: str = "ana") -> ToolContext:
    return ToolContext(session_id=subject, turn_id="t", ports={"idempotency": port})


def test_la_segunda_llamada_devuelve_la_primera_sin_repetir_el_efecto() -> None:
    port, tool = MemoryPort(), Registrar()

    first = execute(tool, context(port), Args(message_sid="SM1"))
    again = execute(tool, context(port), Args(message_sid="SM1", nota="otra"))  # nota no es parte de la clave
    other = execute(tool, context(port, "beto"), Args(message_sid="SM1"))  # otro sujeto, otra clave

    assert tool.effects == 2
    assert (again.deduplicated, again.call_id, again.result) == (True, first.call_id, first.result)
    assert not first.deduplicated
    assert not other.deduplicated


def test_un_error_conocido_libera_la_clave_y_se_puede_reintentar() -> None:
    port, tool = MemoryPort(), Registrar(fail=ToolError("not_found"))

    execute(tool, context(port), Args(message_sid="SM1"))
    tool.fail = None
    retried = execute(tool, context(port), Args(message_sid="SM1"))

    assert (tool.effects, retried.status, retried.deduplicated) == (2, "ok", False)


def test_un_resultado_incierto_deja_la_clave_en_curso_y_no_repite_el_efecto() -> None:
    port, tool = MemoryPort(), Registrar(fail=RuntimeError("se cayó a medias"))

    execute(tool, context(port), Args(message_sid="SM1"))
    tool.fail = None
    blocked = execute(tool, context(port), Args(message_sid="SM1"))

    assert (tool.effects, blocked.status, blocked.error_class) == (1, "error", "in_progress")


def test_dos_llamadas_concurrentes_con_la_misma_clave_hacen_un_solo_efecto() -> None:
    port, tool = MemoryPort(), Registrar()
    start = threading.Barrier(8)
    outcomes: list[str] = []

    def call() -> None:
        start.wait()
        outcome = execute(tool, context(port), Args(message_sid="SM1"))
        outcomes.append(outcome.error_class or ("dedup" if outcome.deduplicated else "ok"))

    threads = [threading.Thread(target=call) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert tool.effects == 1
    assert outcomes.count("ok") == 1


def test_la_clave_es_el_json_canonico_de_los_campos_declarados() -> None:
    same = idempotency_key(("message_sid",), Args(message_sid="SM1", nota="a"))

    assert same == idempotency_key(("message_sid",), Args(message_sid="SM1", nota="b"))
    assert same != idempotency_key(("message_sid",), Args(message_sid="SM2"))
    assert idempotency_key((), Args(message_sid="SM1")) is None
    assert idempotency_key(("message_sid", "nota"), Args(message_sid="SM1")) is None  # no identificable


class Enviar(Registrar):
    name: ClassVar[str] = "enviar"
    kind: ClassVar[Literal["read", "write", "external"]] = "external"
    idempotency_key: ClassVar[tuple[str, ...]] = ()
    idempotency_scope: ClassVar[Literal["subject", "turn"]] = "turn"


def test_por_turno_un_reintento_no_repite_pero_otro_turno_si() -> None:
    port, tool = MemoryPort(), Enviar()

    def call(turn: str) -> None:
        execute(
            tool,
            ToolContext(session_id="ana", turn_id=turn, ports={"idempotency": port}),
            Args(message_sid="x"),
        )

    call("c:1")
    call("c:1")  # el modelo reintenta en el mismo turno
    call("c:2")  # la persona pide un reenvío en otro turno

    assert tool.effects == 2
