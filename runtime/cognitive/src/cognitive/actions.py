"""Acciones: binding, invocación, resultado, ejecución y puerto de persistencia."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from cognitive._base import FrozenModel
from cognitive.jsons import JsonObject, JsonValue
from cognitive.scope import AccessScope, Scope
from ontology import Ref

if TYPE_CHECKING:
    from cognitive.review import ReviewResolution

ImplementationKind = Literal["tool", "deterministic", "llm", "human"]
ActionExecutionStatus = Literal["pending", "running", "succeeded", "failed", "unknown", "cancelled"]

ActionErrorCode = Literal[
    "validation",
    "authorization",
    "timeout",
    "provider",
    "defect",
    "conflict",
    "forbidden",
    "not_found",
    "schema_mismatch",
    "review_required",
    "cancelled",
]


class ActionError(FrozenModel):
    code: ActionErrorCode
    message: str
    retryable: bool = False


class ImplementationBinding(FrozenModel):
    """Binding de ActionRef/hash a un handler registrado y sus capacidades."""

    action_ref: Ref
    action_hash: str
    kind: ImplementationKind
    handler_name: str
    handler_version: str
    capabilities: frozenset[str] = frozenset()


class ActionInvocation(FrozenModel):
    """Reserva e invocación se vinculan al mismo action execution ID (`ref`)."""

    ref: Ref
    action_ref: Ref
    action_hash: str
    release_id: str
    owner_ref: Ref
    actor_assignment_ref: Ref
    inputs: JsonObject | None = None
    scope: Scope
    idempotency_key: str
    process_ref: Ref | None = None
    goal_ref: Ref | None = None


class ActionResult(FrozenModel):
    """Resultado de una ejecución; pending es estado, no success."""

    execution_ref: Ref
    status: ActionExecutionStatus
    output: JsonValue | None = None
    receipt_ref: Ref | None = None
    error: ActionError | None = None
    evidence_refs: tuple[Ref, ...] = ()


class ExecutionReservation(FrozenModel):
    """Resultado de `ActionExecutionStore.reserve`."""

    execution_ref: Ref
    status: Literal["reserved", "duplicate"]
    result: ActionResult | None = None
    revision: int


@runtime_checkable
class ActionExecutionStore(Protocol):
    """Persistencia tipada de ejecuciones; CAS por revision, idempotencia por key+scope."""

    def reserve(self, invocation: ActionInvocation) -> ExecutionReservation: ...
    def start(self, execution_ref: Ref, expected_revision: int, scope: Scope) -> ActionResult: ...
    def complete(
        self, execution_ref: Ref, expected_revision: int, result: ActionResult, scope: Scope
    ) -> ActionResult: ...
    def get(self, execution_ref: Ref, scope: Scope) -> ActionResult | None: ...
    def lookup_process(self, execution_ref: Ref, scope: Scope) -> Ref | None: ...
    def record_review_event(self, resolution: ReviewResolution) -> None: ...


@runtime_checkable
class ActionExecutor(Protocol):
    """Ejecuta una invocación; revalida autorización crítica antes del efecto."""

    def invoke(self, invocation: ActionInvocation, access: AccessScope) -> ActionResult: ...
