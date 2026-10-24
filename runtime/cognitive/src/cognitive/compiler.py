"""Contrato de compilación de máquinas desde el grafo SLDB (api-canonica §compilador).

DTOs estructurales neutrales: sin imports de kb/SLDB. La implementación única de
carga/compilación vive en kb/machines.py (otro worker) y satisface este Protocol;
`SldbDeclarations.machine(ref)` la usa. Evaluación/validación pura vive en el motor.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import Field

from cognitive._base import FrozenModel
from cognitive.guards import GuardExpr
from cognitive.jsons import JsonObject
from cognitive.machine import Cardinality, MachineDefinition, ValueBinding
from ontology import Ref

GraphEdgeKind = Literal[
    "has_state",
    "has_transition",
    "starts_at",
    "transition_from",
    "transition_to",
    "triggered_by",
    "guarded_by",
    "invokes_action",
    "realized_by",
]
GRAPH_EDGE_KINDS: frozenset[str] = frozenset(GraphEdgeKind.__args__)  # type: ignore[attr-defined]


class GraphEdge(FrozenModel):
    """Arista tipada con provenance del documento que la declara."""

    kind: GraphEdgeKind
    source_ref: Ref
    target_ref: Ref
    doc_ref: Ref | None = None


class MachineGraphDoc(FrozenModel):
    """MachineDoc neutral (declaraciones usan refs; el DTO compilado usa IDs locales).

    `variables_schema` preserva el esquema autoral del grafo; el compilador lo
    propaga a `MachineDefinition.variables_schema` (contrato api-canonica §compilador).
    """

    id: str
    title: str
    version: str
    family: str
    initial_state_ref: Ref
    state_refs: tuple[Ref, ...] = ()
    transition_refs: tuple[Ref, ...] = ()
    event_type_refs: tuple[Ref, ...] = ()
    cardinality: Cardinality = "many"
    variables_schema: JsonObject | None = None


class StateGraphDoc(FrozenModel):
    """StateDoc neutral; pertenece a exactamente una máquina."""

    id: str
    machine_ref: Ref
    terminal: bool = False


class TransitionGraphDoc(FrozenModel):
    """TransitionDoc neutral; guard_refs en AND, action_refs en orden.

    `assignments` preserva los bindings autorales; el compilador los propaga a
    `TransitionDefinition.assignments` (ValueBinding: exactamente una de literal
    o snapshot_path).
    """

    id: str
    machine_ref: Ref
    source_ref: Ref
    target_ref: Ref
    event_type_ref: Ref
    priority: int = 0
    guard_refs: tuple[Ref, ...] = ()
    action_refs: tuple[Ref, ...] = ()
    assignments: dict[str, ValueBinding] = Field(default_factory=dict)


class EventTypeGraphDoc(FrozenModel):
    """EventTypeDoc neutral: nombre y payload_schema JSON."""

    id: str
    machine_ref: Ref
    name: str
    payload_schema: JsonObject | None = None


class GuardGraphDoc(FrozenModel):
    """GuardDoc neutral: GuardExpr serializable."""

    id: str
    machine_ref: Ref
    expression: GuardExpr


class MachineGraph(FrozenModel):
    """Subgrafo completo de una máquina para compilar (api-canonica §compilador)."""

    machine: MachineGraphDoc
    states: tuple[StateGraphDoc, ...] = ()
    transitions: tuple[TransitionGraphDoc, ...] = ()
    events: tuple[EventTypeGraphDoc, ...] = ()
    guards: tuple[GuardGraphDoc, ...] = ()
    edges: tuple[GraphEdge, ...] = ()

    def edges_of(self, kind: GraphEdgeKind) -> tuple[GraphEdge, ...]:
        return tuple(e for e in self.edges if e.kind == kind)


@runtime_checkable
class GraphCompiler(Protocol):
    """Compila un MachineGraph a MachineDefinition inmutable con hash estable."""

    def compile(self, graph: MachineGraph) -> MachineDefinition: ...
