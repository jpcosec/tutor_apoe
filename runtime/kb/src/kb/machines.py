"""Compilación de grafo de máquina a `MachineDefinition` inmutable (api-canonica §03).

Carga los documentos de la máquina (MachineDoc, StateDoc, TransitionDoc, EventTypeDoc,
GuardDoc, ActionDoc) y el grafo TIPADO REAL de SLDB (`edges_from`), construye el
`MachineGraph` neutral (contrato `cognitive.compiler`) y lo compila a `MachineDefinition`
con hash canónico estable.

Reglas:
- Los refs authored NO suplen al grafo: cada relación exige arista tipada real de SLDB
  (ref-edge parity).
- Tipos no válidos en schemas/guards/cardinalidad ⇒ error de compilación, nunca `{}`.
- El hash cubre el contenido (`model_dump(mode="json")` del DTO, excluyendo `content_hash`);
  mismo grafo ⇒ mismo hash, reconstruible sin cache.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from pydantic import TypeAdapter, ValidationError

from cognitive import (
    EventTypeGraphDoc,
    GraphEdge,
    GraphEdgeKind,
    GuardExpr,
    GuardGraphDoc,
    MachineDefinition,
    MachineGraph,
    MachineGraphDoc,
    StateDefinition,
    StateGraphDoc,
    TransitionDefinition,
    TransitionGraphDoc,
    ValueBinding,
    machine_definition_hash,
)
from cognitive.jsons import JsonObject
from kb.loading.sldb_gateway import structural_edges
from kb.model.document import Document
from ontology import Ref

MACHINE_DOC = "MachineDoc"
STATE_DOC = "StateDoc"
TRANSITION_DOC = "TransitionDoc"
EVENT_TYPE_DOC = "EventTypeDoc"
GUARD_DOC = "GuardDoc"
ACTION_DOC = "ActionDoc"

_MACHINE_SOURCE = frozenset({"has_state", "has_transition", "starts_at"})
_TRANSITION_SOURCE = frozenset(
    {"transition_from", "transition_to", "triggered_by", "guarded_by", "invokes_action"}
)


class GraphCompileError(Exception):
    """Error semántico de compilación del grafo de una máquina."""


def _bare(node_id: str) -> str:
    """`sldb://document/MachineDoc:m1` -> `MachineDoc:m1`."""
    return node_id.removeprefix("sldb://document/")


def _ref(key: str) -> Ref:
    """`Modelo:nombre` -> `Ref(kind='kb', id='Modelo:nombre')`."""
    return Ref(kind="kb", id=key)


def _typed_ref(key: str, model: str) -> Ref:
    """Normaliza `kb:Model:id@release` / `Model:id` / `id` a local `Model:id`.

    Descarta el prefijo opcional `kb:` y el pin de release `@...` para que el id local
    resultante sea válido para `Ref(kind='kb', id='Model:id')` (sin `@` ni prefijo anidado).
    """
    local = Ref.parse(key).id if key.startswith("kb:") else key
    if "@" in local:
        local = Ref.parse(f"kb:{local}").id
    ref = _ref(local if ":" in local else f"{model}:{local}")
    if ref.id.split(":", 1)[0] != model:
        raise GraphCompileError(f"{key}: expected {model}")
    return ref


def _str_list(payload: dict[str, object], key: str, doc_key: str) -> list[str]:
    raw = payload.get(key, [])
    if not isinstance(raw, list):
        raise GraphCompileError(f"{doc_key}: {key} debe ser una lista de refs, no {type(raw).__name__}")
    values = cast(list[object], raw)
    if not all(isinstance(x, str) for x in values):
        raise GraphCompileError(f"{doc_key}: {key} requires string refs")
    return cast(list[str], values)


def _version(payload: dict[str, object], key: str) -> str:
    value = payload.get("version")
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = cast(list[object], value)
        if parts and all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in parts):
            return ".".join(str(v) for v in parts)
    raise GraphCompileError(f"{key}: invalid authored version")


def _bool_field(payload: dict[str, object], key: str, doc_key: str) -> bool:
    value = payload.get(key, False)
    if value is True or value is False:
        return value
    raise GraphCompileError(f"{doc_key}: {key} debe ser booleano, no {value!r}")


def _int_field(payload: dict[str, object], key: str, doc_key: str) -> int:
    value = payload.get(key, 0)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise GraphCompileError(f"{doc_key}: {key} debe ser entero, no {value!r}")


def _json_object(payload: dict[str, object], key: str, doc_key: str) -> JsonObject | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise GraphCompileError(f"{doc_key}: {key} debe ser un objeto JSON, no {type(value).__name__}")
    try:
        return cast(JsonObject, TypeAdapter(JsonObject).validate_python(value, strict=True))
    except ValidationError as err:
        raise GraphCompileError(f"{doc_key}: invalid JSON {key}") from err


def _guard_doc(doc: Document) -> GuardExpr:
    expr = doc.payload.get("expression")
    if not isinstance(expr, dict):
        raise GraphCompileError(f"{doc.key}: expression debe ser un objeto GuardExpr")
    try:
        return GuardExpr.model_validate(expr)
    except ValidationError as err:
        raise GraphCompileError(f"{doc.key}: guard inválido: {err}") from err


def _assignments(payload: dict[str, object], doc_key: str) -> dict[str, ValueBinding]:
    """Compila assignments authored a `ValueBinding` de forma estricta.

    Usa `ValueBinding.model_validate` para respetar «exactamente una de literal o
    snapshot_path»: literal null permitido, ambas claves → error, sin coerción.
    """
    raw = payload.get("assignments", {})
    if not isinstance(raw, dict):
        raise GraphCompileError(f"{doc_key}: assignments debe ser un objeto")
    result: dict[str, ValueBinding] = {}
    for var, spec in cast(dict[str, object], raw).items():
        if not isinstance(spec, dict):
            raise GraphCompileError(f"assignment {var!r} debe ser un objeto")
        try:
            result[var] = ValueBinding.model_validate(spec)
        except ValidationError as err:
            raise GraphCompileError(f"assignment {var!r} inválido: {err}") from err
    return result


class GraphCompiler:
    """Implementa el `GraphCompiler` neutral: compila un `MachineGraph` a `MachineDefinition`."""

    def compile(self, graph: MachineGraph) -> MachineDefinition:
        machine_key = f"{MACHINE_DOC}:{graph.machine.id}"
        self._validate(graph, machine_key)

        state_defs = tuple(
            StateDefinition(id=s.id, terminal=s.terminal) for s in sorted(graph.states, key=lambda x: x.id)
        )
        initial = graph.machine.initial_state_ref.id.split(":", 1)[-1]
        transition_defs = self._transitions(graph, machine_key, initial)
        self._check_unreachable(initial, transition_defs, [s.id for s in graph.states])

        event_schemas: JsonObject = {}
        for e in sorted(graph.events, key=lambda x: x.name):
            event_schemas[e.name] = e.payload_schema if e.payload_schema is not None else {"type": "object"}
        variables_schema = self._variables_schema(graph)

        definition = MachineDefinition(
            ref=_ref(machine_key),
            version=graph.machine.version,
            content_hash="",
            family=graph.machine.family,
            initial_state=initial,
            states=state_defs,
            transitions=tuple(transition_defs),
            event_schemas=event_schemas,
            cardinality=graph.machine.cardinality,
            variables_schema=variables_schema,
        )
        # Fuente única de hash: el helper oficial del core (mismo payload -> mismo hash,
        # compilador, core y engine convergen; nunca model_dump).
        content_hash = machine_definition_hash(definition)
        return definition.model_copy(update={"content_hash": content_hash})

    # -- validación -----------------------------------------------------------

    def _validate(self, graph: MachineGraph, machine_key: str) -> None:
        machine_ref = _ref(machine_key)
        for edge in graph.edges:
            if edge.kind in _MACHINE_SOURCE and edge.source_ref != machine_ref:
                raise GraphCompileError(f"{machine_key}: wrong machine edge source")
            if edge.kind == "realized_by" and (
                edge.source_ref.id.split(":", 1)[0] != "ProcessDoc" or edge.target_ref != machine_ref
            ):
                raise GraphCompileError(f"{machine_key}: invalid realized_by endpoints")
        transition_refs = {_ref(f"TransitionDoc:{t.id}") for t in graph.transitions}
        for edge in graph.edges:
            if edge.kind in _TRANSITION_SOURCE and edge.source_ref not in transition_refs:
                raise GraphCompileError(f"{machine_key}: edge from unknown transition")
        names = [event.name for event in graph.events]
        if len(set(names)) != len(names):
            raise GraphCompileError(f"{machine_key}: duplicate event names")
        self._check_owner(graph, machine_key, machine_ref)
        self._check_cardinality(graph, machine_key)
        starts = graph.edges_of("starts_at")
        if len(starts) != 1:
            raise GraphCompileError(f"{machine_key}: starts_at debe tener exactamente una arista real")
        if starts[0].source_ref != machine_ref or starts[0].target_ref != graph.machine.initial_state_ref:
            raise GraphCompileError(f"{machine_key}: starts_at differs from authored initial_state_ref")
        if not graph.states:
            raise GraphCompileError(f"{machine_key}: requires states")
        if not self._initial_in_states(graph):
            raise GraphCompileError(f"{machine_key}: estado inicial no está en has_state")
        for t in graph.transitions:
            tkey = f"{TRANSITION_DOC}:{t.id}"
            self._transition_parity(graph, tkey, t)
            state_refs = {_ref(f"StateDoc:{s.id}") for s in graph.states}
            if t.source_ref not in state_refs or t.target_ref not in state_refs:
                raise GraphCompileError(f"{tkey}: endpoint outside machine")
            guard_refs = {_ref(f"GuardDoc:{g.id}") for g in graph.guards}
            if not set(t.guard_refs) <= guard_refs:
                raise GraphCompileError(f"{tkey}: unresolved guard")
        for kind, authored in (
            ("has_state", graph.machine.state_refs),
            ("has_transition", graph.machine.transition_refs),
        ):
            actual = {e.target_ref for e in graph.edges_of(cast(GraphEdgeKind, kind))}
            if actual != set(authored):
                raise GraphCompileError(f"{machine_key}: {kind} differs from authored refs")
        if set(graph.machine.event_type_refs) != {_ref(f"EventTypeDoc:{e.id}") for e in graph.events}:
            raise GraphCompileError(f"{machine_key}: event refs differ from owned events")

    @staticmethod
    def _initial_in_states(graph: MachineGraph) -> bool:
        initial = graph.machine.initial_state_ref.id
        keys = {s.id for s in graph.states} | {f"{STATE_DOC}:{s.id}" for s in graph.states}
        return initial in keys

    def _check_owner(self, graph: MachineGraph, machine_key: str, machine_ref: Ref) -> None:
        for s in graph.states:
            if s.machine_ref != machine_ref:
                raise GraphCompileError(f"{STATE_DOC}:{s.id}: machine_ref no es {machine_key}")
        for t in graph.transitions:
            if t.machine_ref != machine_ref:
                raise GraphCompileError(f"{TRANSITION_DOC}:{t.id}: machine_ref no es {machine_key}")
        for e in graph.events:
            if e.machine_ref != machine_ref:
                raise GraphCompileError(f"{EVENT_TYPE_DOC}:{e.id}: machine_ref no es {machine_key}")
        for g in graph.guards:
            if g.machine_ref != machine_ref:
                raise GraphCompileError(f"{GUARD_DOC}:{g.id}: machine_ref no es {machine_key}")

    def _check_cardinality(self, graph: MachineGraph, machine_key: str) -> None:
        authored_states = {f"{STATE_DOC}:{s.id}" for s in graph.states}
        edge_states = {e.target_ref.id for e in graph.edges_of("has_state")}
        if authored_states != edge_states:
            diff = f"{sorted(edge_states)} vs {sorted(authored_states)}"
            raise GraphCompileError(f"{machine_key}: has_state no cuadra con los estados ({diff})")
        authored_transitions = {f"{TRANSITION_DOC}:{t.id}" for t in graph.transitions}
        edge_transitions = {e.target_ref.id for e in graph.edges_of("has_transition")}
        if authored_transitions != edge_transitions:
            raise GraphCompileError(
                f"{machine_key}: has_transition no cuadra con las transiciones "
                f"({sorted(edge_transitions)} vs {sorted(authored_transitions)})"
            )

    def _transition_parity(self, graph: MachineGraph, tkey: str, t: TransitionGraphDoc) -> None:
        def _expect(kind: GraphEdgeKind, targets: set[Ref]) -> None:
            actual = {e.target_ref for e in graph.edges_of(kind) if e.source_ref.id == tkey}
            if actual != set(targets):
                raise GraphCompileError(f"{tkey}: {kind} no cuadra con refs authored ({actual} vs {targets})")

        _expect("transition_from", {t.source_ref})
        _expect("transition_to", {t.target_ref})
        _expect("triggered_by", {t.event_type_ref})
        _expect("guarded_by", set(t.guard_refs))
        _expect("invokes_action", set(t.action_refs))

    # -- construcción ---------------------------------------------------------

    def _transitions(
        self, graph: MachineGraph, machine_key: str, initial_local: str
    ) -> list[TransitionDefinition]:
        events_by_ref = {e.id: e for e in graph.events}
        guards_by_ref = {g.id: g for g in graph.guards}
        result: list[TransitionDefinition] = []
        for t in sorted(graph.transitions, key=lambda x: x.id):
            event = events_by_ref.get(t.event_type_ref.id.split(":", 1)[-1])
            if event is None:
                message = (
                    f"{TRANSITION_DOC}:{t.id}: event_type_ref "
                    f"{t.event_type_ref} no resuelve a un EventTypeDoc"
                )
                raise GraphCompileError(message)
            guard_exprs = tuple(
                guards_by_ref[g_ref.id.split(":", 1)[-1]].expression for g_ref in t.guard_refs
            )
            result.append(
                TransitionDefinition(
                    id=t.id,
                    source=t.source_ref.id.split(":", 1)[-1],
                    target=t.target_ref.id.split(":", 1)[-1],
                    event_type=event.name,
                    priority=t.priority,
                    guards=guard_exprs,
                    action_refs=tuple(_ref(a.id) for a in t.action_refs),
                    assignments=t.assignments,
                )
            )
        return result

    def _variables_schema(self, graph: MachineGraph) -> JsonObject:
        # Preserva el schema autoral del MachineDoc cuando existe; si el autor no declaró
        # variables, default canónico object. Nunca inventa schema.
        schema = graph.machine.variables_schema
        if schema is None:
            return {"type": "object"}
        return dict(schema)

    @staticmethod
    def _check_unreachable(
        initial: str, transitions: list[TransitionDefinition], state_ids: list[str]
    ) -> None:
        reachable = {initial}
        changed = True
        while changed:
            changed = False
            for t in transitions:
                if t.source in reachable and t.target not in reachable:
                    reachable.add(t.target)
                    changed = True
        unreachable = set(state_ids) - reachable
        if unreachable:
            raise GraphCompileError(f"estados inalcanzables: {sorted(unreachable)}")


class SldbGraphLoader:
    """Carga el `MachineGraph` neutral de una máquina: documentos KB + grafo TIPADO real SLDB."""

    def __init__(self, store: Path, *, pythonpath: str | None = None) -> None:
        self._store = store
        self._pythonpath = pythonpath

    def load(self, documents: list[Document], machine_ref: Ref | str) -> MachineGraph:
        target = _typed_ref(machine_ref, MACHINE_DOC).id if isinstance(machine_ref, str) else machine_ref.id
        by_key = {d.key: d for d in documents}
        machine_doc = by_key.get(target)
        if machine_doc is None:
            raise GraphCompileError(f"no hay {MACHINE_DOC} {target!r}")
        payload = machine_doc.payload

        state_refs = _str_list(payload, "state_refs", target)
        transition_refs = _str_list(payload, "transition_refs", target)
        event_refs = _str_list(payload, "event_type_refs", target)
        cardinality = str(payload.get("cardinality") or "many")
        if cardinality not in ("many", "one_active_per_owner"):
            raise GraphCompileError(f"{target}: cardinality inválida {cardinality!r}")

        machine = MachineGraphDoc(
            id=str(payload["id"]),
            title=str(payload.get("title") or ""),
            version=_version(payload, target),
            family=str(payload.get("family") or ""),
            initial_state_ref=_typed_ref(str(payload.get("initial_state_ref") or ""), STATE_DOC),
            state_refs=tuple(_typed_ref(r, STATE_DOC) for r in state_refs),
            transition_refs=tuple(_typed_ref(r, TRANSITION_DOC) for r in transition_refs),
            event_type_refs=tuple(_typed_ref(r, EVENT_TYPE_DOC) for r in event_refs),
            cardinality=cardinality,
            variables_schema=_json_object(payload, "variables_schema", target),
        )

        owned_states = [
            d for d in documents if d.model == STATE_DOC and d.payload.get("machine_ref") == target
        ]
        owned_transitions = [
            d for d in documents if d.model == TRANSITION_DOC and d.payload.get("machine_ref") == target
        ]
        owned_events = [
            d for d in documents if d.model == EVENT_TYPE_DOC and d.payload.get("machine_ref") == target
        ]
        owned_guards = [
            d for d in documents if d.model == GUARD_DOC and d.payload.get("machine_ref") == target
        ]

        for relation, owned in (("has_state", owned_states), ("has_transition", owned_transitions)):
            membership = structural_edges(self._store, relation)
            for document in owned:
                owners = {source for source, destination in membership if destination == document.key}
                if owners != {target}:
                    raise GraphCompileError(f"{document.key}: requires exactly one graph owner {target}")

        states = tuple(
            StateGraphDoc(
                id=str(d.payload["id"]),
                machine_ref=_ref(target),
                terminal=_bool_field(d.payload, "terminal", d.key),
            )
            for d in sorted(owned_states, key=lambda x: x.key)
        )
        transitions = tuple(
            TransitionGraphDoc(
                id=str(d.payload["id"]),
                machine_ref=_ref(target),
                source_ref=_typed_ref(str(d.payload["source_ref"]), STATE_DOC),
                target_ref=_typed_ref(str(d.payload["target_ref"]), STATE_DOC),
                event_type_ref=_typed_ref(str(d.payload["event_type_ref"]), EVENT_TYPE_DOC),
                priority=_int_field(d.payload, "priority", d.key),
                guard_refs=tuple(_typed_ref(g, GUARD_DOC) for g in _str_list(d.payload, "guard_refs", d.key)),
                action_refs=tuple(
                    _typed_ref(a, ACTION_DOC) for a in _str_list(d.payload, "action_refs", d.key)
                ),
                assignments=_assignments(d.payload, d.key),
            )
            for d in sorted(owned_transitions, key=lambda x: x.key)
        )
        events = tuple(
            EventTypeGraphDoc(
                id=str(d.payload["id"]),
                machine_ref=_ref(target),
                name=str(d.payload["name"]),
                payload_schema=_json_object(d.payload, "payload_schema", d.key),
            )
            for d in sorted(owned_events, key=lambda x: x.key)
        )
        guards = tuple(
            GuardGraphDoc(id=str(d.payload["id"]), machine_ref=_ref(target), expression=_guard_doc(d))
            for d in sorted(owned_guards, key=lambda x: x.key)
        )

        for transition in transitions:
            for action in transition.action_refs:
                document = by_key.get(action.id)
                if document is None or not document.is_a(ACTION_DOC):
                    raise GraphCompileError(f"{transition.id}: unresolved ActionDoc {action}")
        edges = self._read_edges(target, [f"{TRANSITION_DOC}:{t.id}" for t in transitions])
        for source, destination in structural_edges(self._store, "realized_by"):
            if destination == target:
                process = by_key.get(source)
                if process is None or not process.is_a("ProcessDoc"):
                    raise GraphCompileError(f"{source}: invalid realized_by source")
                refs = _str_list(process.payload, "machine_refs", source)
                if _ref(target) not in {_typed_ref(r, MACHINE_DOC) for r in refs}:
                    raise GraphCompileError(f"{source}: realized_by differs from authored machine_refs")
        for process in documents:
            if process.is_a("ProcessDoc"):
                refs = {
                    _typed_ref(r, MACHINE_DOC)
                    for r in _str_list(process.payload, "machine_refs", process.key)
                }
                actual = {
                    _ref(destination)
                    for source, destination in structural_edges(self._store, "realized_by")
                    if source == process.key
                }
                if _ref(target) in refs and actual != refs:
                    raise GraphCompileError(f"{process.key}: realized_by differs from authored machine_refs")
        return MachineGraph(
            machine=machine, states=states, transitions=transitions, events=events, guards=guards, edges=edges
        )

    def _read_edges(self, machine_key: str, transition_keys: list[str]) -> tuple[GraphEdge, ...]:
        edges: list[GraphEdge] = []
        for rel in _MACHINE_SOURCE:
            edges.extend(self._fetch(machine_key, rel))
        for tkey in transition_keys:
            for rel in _TRANSITION_SOURCE:
                edges.extend(self._fetch(tkey, rel))
        for source, target in structural_edges(self._store, "realized_by"):
            if target == machine_key:
                edges.append(GraphEdge(kind="realized_by", source_ref=_ref(source), target_ref=_ref(target)))
        # dedupe
        seen: set[tuple[str, str, str]] = set()
        out: list[GraphEdge] = []
        for e in edges:
            key = (e.kind, str(e.source_ref), str(e.target_ref))
            if key in seen:
                continue
            seen.add(key)
            out.append(e)
        return tuple(sorted(out, key=lambda e: (e.kind, str(e.source_ref), str(e.target_ref))))

    def _fetch(self, export_id: str, relation: str) -> list[GraphEdge]:
        records = [
            (source, target)
            for source, target in structural_edges(self._store, relation)
            if source == export_id
        ]
        result: list[GraphEdge] = []
        for source, target in records:
            result.append(
                GraphEdge(
                    kind=cast(GraphEdgeKind, relation),
                    source_ref=_ref(_bare(source)),
                    target_ref=_ref(_bare(target)),
                )
            )
        return result


def canonical_hash(blob: object) -> str:
    """SHA256 canónico de un objeto JSON-serializable (orden estable, UTF-8)."""
    return hashlib.sha256(
        json.dumps(blob, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def collect_machine_graph(
    documents: list[Document],
    store: Path | None,
    *,
    pythonpath: str | None = None,
    machine_ref: Ref | str | None = None,
) -> MachineGraph:
    """Carga el `MachineGraph` de una máquina; `store` obligatorio (grafo real SLDB)."""
    if store is None:
        raise GraphCompileError("collect_machine_graph exige un store SLDB para leer el grafo real")
    loader = SldbGraphLoader(store, pythonpath=pythonpath)
    if machine_ref is None:
        machines = [d for d in documents if d.model == MACHINE_DOC]
        if len(machines) != 1:
            raise GraphCompileError(f"se esperaba exactamente una máquina, hay {len(machines)}")
        machine_ref = machines[0].key
    return loader.load(documents, machine_ref)


__all__ = [
    "GraphCompileError",
    "GraphCompiler",
    "MachineGraph",
    "SldbGraphLoader",
    "canonical_hash",
    "collect_machine_graph",
]
