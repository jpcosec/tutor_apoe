"""Self y actores: asignación, binding, runtime y persistencia tipada."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from cognitive._base import FrozenModel
from cognitive.actions import ActionError
from cognitive.context import ContextSnapshot
from cognitive.jsons import JsonObject, JsonValue
from cognitive.scope import Scope
from ontology import Ref

ActorKind = Literal["llm", "deterministic", "human"]
ActorResultStatus = Literal["completed", "pending", "failed"]


class SelfAssignment(FrozenModel):
    """Vínculo SelfDoc -> actor con capacidades efectivas y revisión de autoridad."""

    ref: Ref
    self_definition_ref: Ref
    self_definition_hash: str
    actor_ref: Ref
    scope: Scope
    granted_capabilities: frozenset[str] = frozenset()
    machine_ref: Ref | None = None
    revision: int = 0


class ActorBinding(FrozenModel):
    """Registro de implementación de un Self (LLM/código/humano)."""

    self_ref: Ref
    self_hash: str
    kind: ActorKind
    handler_name: str
    handler_version: str
    output_schema: JsonObject | None = None


class ActorResult(FrozenModel):
    """Salida de un ActorRuntime; solo output conforme selecciona ActionInvocation."""

    actor_assignment_ref: Ref
    status: ActorResultStatus
    output: JsonValue | None = None
    evidence_refs: tuple[Ref, ...] = ()
    error: ActionError | None = None


@runtime_checkable
class ActorRuntime(Protocol):
    """Ejecuta un Self sobre un ContextSnapshot; implementación intercambiable."""

    def run(self, context: ContextSnapshot, input: JsonValue | None = None) -> ActorResult: ...


@runtime_checkable
class ActorRegistry(Protocol):
    """Registro de bindings y resolución por SelfAssignment."""

    def register(self, binding: ActorBinding) -> None: ...
    def resolve(self, assignment: SelfAssignment) -> ActorRuntime: ...


@runtime_checkable
class SelfAssignmentStore(Protocol):
    """Persistencia tipada de SelfAssignment (no structs de Context)."""

    def create(self, assignment: SelfAssignment) -> SelfAssignment: ...
    def load(self, ref: Ref, scope: Scope) -> SelfAssignment | None: ...
    def list_by_actor(self, actor_ref: Ref, scope: Scope) -> tuple[SelfAssignment, ...]: ...
