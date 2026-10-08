"""Idempotencia de tools (03 I7, D11, D15): una clave por llamada y el puerto que la reserva.

Con `idempotency_key`, el efecto ocurre a lo más una vez por clave y sujeto. La clave se reserva
antes del efecto; un resultado `ok` se guarda para las llamadas siguientes; un error conocido
libera la clave; un resultado incierto (defecto o `commit_failed`) la deja `pending` y nadie
vuelve a ejecutar el efecto hasta que se reconcilie a mano (`release`).
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal, Protocol

from pydantic import BaseModel

from tools.contract import ErrorClass

#: En una tool externa, errores tras los que no se sabe si el efecto ocurrió: la reserva queda
#: `pending`. En una local no hace falta: la unidad de trabajo revierte efecto y reserva juntos.
UNCERTAIN: frozenset[ErrorClass] = frozenset({"defect", "commit_failed"})


class ReservationLike(Protocol):
    @property
    def state(self) -> Literal["owned", "done", "pending"]: ...
    @property
    def call_id(self) -> str: ...
    @property
    def outcome(self) -> dict[str, object] | None: ...


class IdempotencyPort(Protocol):
    """Lo que implementa 02 (`SqlStore`), en `ToolContext.ports["idempotency"]`."""

    def reserve(self, name: str, key: str, subject: str, call_id: str) -> ReservationLike: ...
    def complete(
        self, name: str, key: str, subject: str, call_id: str, outcome: dict[str, object]
    ) -> None: ...
    def release(self, name: str, key: str, subject: str, call_id: str) -> None: ...


def idempotency_key(fields: tuple[str, ...], args: BaseModel, turn: str | None = None) -> str | None:
    """`sha256` del JSON canónico de `{campo: valor}` (D11), más el turno si la tool deduplica por
    turno. Si un campo declarado viene vacío, la llamada no se puede identificar y corre sin
    idempotencia; sin campos ni turno, tampoco: None."""
    values = args.model_dump(mode="json")
    if (not fields and turn is None) or any(values.get(f) is None for f in fields):
        return None
    mapping: dict[str, object] = {f: values[f] for f in fields}
    if turn is not None:
        mapping["__turn__"] = turn
    canonical = json.dumps(mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()
