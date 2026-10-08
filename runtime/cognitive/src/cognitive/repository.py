"""Puertos neutrales de persistencia: máquina, timers y evidencia (api-canonica §repositorio)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from cognitive._base import FrozenModel
from cognitive.events import Event, ExternalReceipt, Observation
from cognitive.jsons import JsonValue
from cognitive.machine import MachineCommand, MachineInstance, TimerSpec, TransitionDecision
from cognitive.scope import Scope
from ontology import Ref
from ontology.canonical import canonical_json


def invocation_fingerprint(operation: str, args: Mapping[str, JsonValue]) -> str:
    """Huella canónica de una invocación externa (operación + args).

    SHA256 de canonical_json; sirve para dedupe durable de recepción: dos
    llamadas con la misma huella son la misma invocación, no una segunda
    llamada al provider (evita doble efecto).
    """
    return hashlib.sha256(
        canonical_json({"operation": operation, "args": dict(args)})
    ).hexdigest()


class ReceiptReservation(FrozenModel):
    """Reserva durable de un receipt de invocación externa (dueño + huella).

    El adapter reserva ANTES de llamar al provider: `duplicate` con la misma
    huella reutiliza el receipt; `conflict` indica mismo invocation_id con
    huella distinta (no llamar al provider). SQL durable en data.
    """

    ref: Ref
    invocation_id: str
    operation: str
    owner_ref: Ref
    scope: Scope
    input_fingerprint: str
    status: Literal["reserved", "duplicate", "conflict"]
    revision: str


@runtime_checkable
class MachineRepository(Protocol):
    """Persistencia de instancias; CAS por revision, dedupe idempotente en inbox.

    Semántica durable (api-canonica):
    - commit graba estado+transición+inbox+outbox en una unidad; CAS revision.
    - duplicado (mismo event_id+payload+source) no produce segunda transición;
      mismo id con payload/source distintos lanza EventCollisionError.
    - record_rejection guarda rechazo en inbox de forma idempotente.
    - create valida cardinalidad one_active_per_owner cuando corresponde.
    """

    def create(self, instance: MachineInstance, cardinality: str = "many") -> MachineInstance: ...
    def load(self, ref: Ref, scope: Scope) -> MachineInstance: ...
    def list_by_owner(self, owner: Ref, scope: Scope) -> tuple[MachineInstance, ...]: ...
    def commit(self, decision: TransitionDecision, event: Event) -> MachineInstance: ...
    def record_rejection(self, instance_ref: Ref, event: Event, reason: str) -> None: ...


@runtime_checkable
class InboxStore(Protocol):
    """Inbox idempotente por client_id+instance_ref+event_id (estado por duplicado)."""

    def has_processed(self, instance_ref: Ref, event: Event, scope: Scope) -> bool: ...
    def rejection_reason(self, instance_ref: Ref, event: Event, scope: Scope) -> str | None: ...
    def collision(self, instance_ref: Ref, event: Event, scope: Scope) -> bool: ...


@runtime_checkable
class OutboxStore(Protocol):
    """Outbox de comandos pendientes con status/attempts; publisher fallido no se marca delivered."""

    def enqueue(self, command: MachineCommand, scope: Scope) -> None: ...
    def pending(self, scope: Scope) -> tuple[MachineCommand, ...]: ...
    def mark_delivered(self, command_id: str, scope: Scope) -> None: ...
    def mark_failed(self, command_id: str, scope: Scope, error: str) -> None: ...


@runtime_checkable
class MachineTimerRepository(Protocol):
    """Timers durables con reloj inyectable en el productor."""

    def schedule(self, timer: TimerSpec) -> None: ...
    def cancel(self, timer_id: str, scope: Scope) -> None: ...
    def due(self, now: datetime, scope: Scope) -> tuple[TimerSpec, ...]: ...
    def mark_published(self, timer_id: str, scope: Scope) -> None: ...


#: Alias de consumidores para el mismo puerto.
TimerRepository = MachineTimerRepository


@runtime_checkable
class WorldEvidenceRepository(Protocol):
    """Evidencia neutral: observaciones y receipts con revisión/CAS (api-canonica §persistencia).

    reconcile_receipt persiste el estado reconciliado explícito (`updated`) por CAS
    sobre `expected_revision`; los comandos opcionales se emiten con el mismo UoW.
    reserve_receipt es la reserva durable previa a la llamada al provider.
    """

    def put_observation(self, observation: Observation) -> None: ...
    def put_receipt(self, receipt: ExternalReceipt) -> None: ...
    def get_observation(self, ref: Ref, scope: Scope) -> Observation | None: ...
    def get_receipt(self, ref: Ref, scope: Scope) -> ExternalReceipt | None: ...
    def reserve_receipt(
        self,
        invocation_id: str,
        operation: str,
        args: Mapping[str, JsonValue],
        owner_ref: Ref,
        scope: Scope,
        status: Literal["pending", "accepted", "confirmed", "rejected", "unknown"] = "pending",
    ) -> ReceiptReservation: ...
    def reconcile_receipt(
        self,
        ref: Ref,
        updated: ExternalReceipt,
        expected_revision: str,
        scope: Scope,
        commands: tuple[MachineCommand, ...] = (),
    ) -> ExternalReceipt: ...
