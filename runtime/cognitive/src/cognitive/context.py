"""Snapshot de contexto: proyección autorizada e inmutable para agentes y guards."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from pydantic import Field

from cognitive._base import FrozenModel
from cognitive.jsons import JsonValue
from cognitive.scope import Scope
from ontology import Ref

#: Snapshot de guard: Mapping[str, JSON] con secciones world/machines/actor/event.
Snapshot = dict[str, JsonValue]


class ContextSnapshot(FrozenModel):
    """Proyección reconstruible por ContextProjector; no cambia source state."""

    self_assignment_ref: Ref
    execution_scope_ref: Ref
    scope: Scope
    definition_refs: tuple[Ref, ...] = ()
    definition_hashes: dict[str, str] = Field(default_factory=dict)
    machine_snapshots: tuple[dict[str, JsonValue], ...] = ()
    observations: tuple[dict[str, JsonValue], ...] = ()
    goal_refs: tuple[Ref, ...] = ()
    goal_status: dict[str, str] = Field(default_factory=dict)
    allowed_action_refs: tuple[Ref, ...] = ()
    knowledge_versions: tuple[Ref, ...] = ()
    activation_refs: tuple[Ref, ...] = ()
    projection_hash: str = ""
    inclusion_reasons: Mapping[str, tuple[str, ...]] = Field(default_factory=dict)


@runtime_checkable
class SnapshotBuilder(Protocol):
    """Constructor puro del snapshot {world, machines, actor, event} para evaluación."""

    def build(
        self,
        *,
        observations: Mapping[str, JsonValue],
        machines: Mapping[str, JsonValue],
        actor: Mapping[str, JsonValue],
        event: Mapping[str, JsonValue],
    ) -> Snapshot: ...


@runtime_checkable
class ContextProjector(Protocol):
    """Dueño del snapshot autorizado para un SelfAssignment + execution_scope."""

    def project(self, self_assignment: Ref, execution_scope: Ref, scope: Scope) -> ContextSnapshot: ...
