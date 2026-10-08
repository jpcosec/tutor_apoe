"""DTOs de máquina: definición, instancia, decisión, comandos y timers.

Colecciones de definición son tuplas; snapshots/definiciones frozen + extra=forbid.
Mutar la instancia produce una nueva revisión, no cambia el snapshot evaluado.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from cognitive._base import FrozenModel
from cognitive._time import Utc
from cognitive.guards import GuardEvidence, GuardExpr
from cognitive.jsons import JsonValue
from cognitive.scope import Scope
from ontology import Ref

Cardinality = Literal["many", "one_active_per_owner"]


class StateDefinition(FrozenModel):
    id: str
    terminal: bool = False


class ValueBinding(FrozenModel):
    """Asignación de variable: exactamente una de literal JSON o snapshot_path.

    `literal=None` explícito es un literal JSON válido (null); se distingue de
    "ausente" por `model_fields_set`.
    """

    literal: JsonValue | None = None
    snapshot_path: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _exactamente_una(self) -> ValueBinding:
        literal_set = "literal" in self.model_fields_set
        path_set = "snapshot_path" in self.model_fields_set
        if literal_set == path_set:
            raise ValueError("ValueBinding exige exactamente una de literal o snapshot_path")
        return self

    @property
    def is_literal(self) -> bool:
        return "literal" in self.model_fields_set


class TransitionDefinition(FrozenModel):
    """Transición declarada; guards en AND, orden de action_refs preservado."""

    id: str
    source: str
    target: str
    event_type: str
    priority: int = 0
    guards: tuple[GuardExpr, ...] = ()
    action_refs: tuple[Ref, ...] = ()
    assignments: dict[str, ValueBinding] = Field(default_factory=dict)


class MachineDefinition(FrozenModel):
    """Definición compilada e inmutable; el hash cubre el contenido canónico."""

    ref: Ref
    version: str
    content_hash: str
    family: str
    initial_state: str
    states: tuple[StateDefinition, ...]
    transitions: tuple[TransitionDefinition, ...]
    event_schemas: dict[str, JsonValue] = Field(default_factory=dict)
    cardinality: Cardinality = "many"
    variables_schema: dict[str, JsonValue] = Field(default_factory=dict)

    def state(self, state_id: str) -> StateDefinition:
        return next(s for s in self.states if s.id == state_id)

    def transitions_for(
        self, state_id: str, event_type: str
    ) -> tuple[TransitionDefinition, ...]:
        return tuple(
            t for t in self.transitions if t.source == state_id and t.event_type == event_type
        )


class MachineInstance(FrozenModel):
    """Instancia viva; revision avanza con cada commit (CAS)."""

    ref: Ref
    definition_ref: Ref
    definition_hash: str
    release_id: str
    owner_ref: Ref
    scope: Scope
    state: str
    revision: int = 0
    created_at: Utc
    updated_at: Utc
    variables: dict[str, JsonValue] = Field(default_factory=dict)

    def with_state(
        self, state: str, revision: int, variables: dict[str, JsonValue], now: Utc
    ) -> MachineInstance:
        return self.model_copy(
            update={"state": state, "revision": revision, "variables": variables, "updated_at": now}
        )


class MachineCommand(FrozenModel):
    """Comando pendiente de una decisión; id estable = sha256(array canónico)."""

    id: str
    kind: Literal["action", "event"]
    target_ref: Ref
    payload: JsonValue = None
    scope: Scope
    correlation_id: str
    causation_id: str | None = None


class TransitionDecision(FrozenModel):
    """Resultado puro de `StateMachine.evaluate`; no persiste nada."""

    instance_ref: Ref
    event_id: str
    expected_revision: int
    previous_state: str
    next_state: str
    transition_ref: str
    snapshot_hash: str
    guard_evidence: tuple[GuardEvidence, ...] = ()
    commands: tuple[MachineCommand, ...] = ()
    variables: dict[str, JsonValue] = Field(default_factory=dict)


class TimerSpec(FrozenModel):
    """Timer durable; id = sha256([instance_ref, name, due_at.isoformat(), definition_hash])."""

    id: str
    instance_ref: Ref
    name: str
    due_at: Utc
    event_type: str
    payload: JsonValue = None
    scope: Scope
    correlation_id: str
    causation_id: str | None = None


def _guard_payload(guard: GuardExpr) -> JsonValue:
    return {
        "op": guard.op,
        "path": list(guard.path),
        "value": guard.value,
        "children": [_guard_payload(c) for c in guard.children],
    }


def machine_definition_payload(definition: MachineDefinition) -> dict[str, JsonValue]:
    """Contenido canónico de una definición para hash/auditoría.

    Ref como texto, JSON ordenado, UTF-8, sin timestamps derivados. Helper único
    compartido por compilador y motor: mismo payload => mismo hash, sin importar
    si la fuente es un grafo SLDB o un fixture.
    """
    return {
        "ref": str(definition.ref),
        "version": definition.version,
        "family": definition.family,
        "initial_state": definition.initial_state,
        "states": [
            {"id": s.id, "terminal": s.terminal} for s in definition.states
        ],
        "transitions": [
            {
                "id": t.id,
                "source": t.source,
                "target": t.target,
                "event_type": t.event_type,
                "priority": t.priority,
                "guards": [_guard_payload(g) for g in t.guards],
                "action_refs": [str(a) for a in t.action_refs],
                "assignments": {
                    name: (
                        {"literal": binding.literal}
                        if binding.is_literal
                        else {"snapshot_path": list(binding.snapshot_path)}
                    )
                    for name, binding in t.assignments.items()
                },
            }
            for t in definition.transitions
        ],
        "event_schemas": dict(definition.event_schemas),
        "cardinality": definition.cardinality,
        "variables_schema": dict(definition.variables_schema),
    }


def machine_definition_hash(definition: MachineDefinition) -> str:
    """SHA256 hex del payload canónico (JSON ordenado UTF-8)."""
    from ontology.canonical import canonical_json

    return hashlib.sha256(canonical_json(machine_definition_payload(definition))).hexdigest()
