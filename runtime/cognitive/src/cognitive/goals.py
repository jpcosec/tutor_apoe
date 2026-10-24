"""Goals: instancia, evidencia, assessment y persistencia tipada."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cognitive._base import FrozenModel
from cognitive._time import Utc
from cognitive.jsons import JsonValue
from cognitive.scope import Scope
from ontology import Ref

GoalStatus = str  # estados del grafo: inactive/active/suspended/achieved/failed/abandoned


class GoalInstance(FrozenModel):
    """Instancia de GoalDoc fijada a definición/hash, owner y máquina."""

    ref: Ref
    goal_definition_ref: Ref
    goal_definition_hash: str
    owner_ref: Ref
    scope: Scope
    machine_ref: Ref
    evidence_refs: tuple[Ref, ...] = ()
    status: GoalStatus = "inactive"
    revision: int = 0


class GoalEvidence(FrozenModel):
    """Snapshot para evaluar criterio: {world, machines, actor, event}."""

    snapshot: dict[str, JsonValue]
    required_evidence: tuple[Ref, ...] = ()


class GoalAssessment(FrozenModel):
    """Resultado de evaluar el criterio declarado; no es logro por sí mismo."""

    goal_ref: Ref
    criterion_hash: str
    evidence_refs: tuple[Ref, ...]
    snapshot_hash: str
    assessed_at: Utc
    satisfied: bool


@runtime_checkable
class GoalStore(Protocol):
    """Persistencia tipada de GoalInstance."""

    def create(self, instance: GoalInstance) -> GoalInstance: ...
    def load(self, ref: Ref, scope: Scope) -> GoalInstance | None: ...
    def update(self, instance: GoalInstance) -> GoalInstance: ...
    def list_by_owner(self, owner: Ref, scope: Scope) -> tuple[GoalInstance, ...]: ...
