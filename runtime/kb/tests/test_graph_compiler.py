"""Compilación del grafo de máquina: validación de cardinalidad/endpoints/hash (canonical §03).

Usa el mismo fixture real SLDB de `test_primitive_loading` y ejercita el `GraphCompiler`
neutral: determinismo y estabilidad del hash, cambio de hash ante edición del contenido,
validación de cardinalidad (has_state/starts_at), endpoints de transición y pertenencia.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from machine_fixture import build_machine_store, default_docs, default_edges
from pydantic import ValidationError

from kb import KnowledgeBase
from kb.declarations import SldbDeclarations
from kb.machines import GraphCompileError


def _decl(tmp_path: Path) -> SldbDeclarations:
    ms = build_machine_store(tmp_path)
    return SldbDeclarations(KnowledgeBase.open(ms.root), store=ms.store)


def _edit_and_recompile(tmp_path: Path, mutate: list[tuple[str, str, dict[str, object]]]) -> SldbDeclarations:
    ms = build_machine_store(tmp_path, docs=mutate)
    return SldbDeclarations(KnowledgeBase.open(ms.root), store=ms.store)


def test_hash_estable_y_determinista(tmp_path: Path) -> None:
    decl = _decl(tmp_path)
    md1 = decl.machine("MachineDoc:m1")
    md2 = decl.machine("MachineDoc:m1")
    assert md1.content_hash == md2.content_hash


def test_hash_cubre_contenido(tmp_path: Path) -> None:
    md1 = _decl(tmp_path).machine("MachineDoc:m1")
    # versión distinta ⇒ contenido distinto ⇒ hash distinto.
    docs = default_docs()
    docs[0] = ("MachineDoc", "m1.md", {**docs[0][2], "version": "1.1"})
    md2 = _edit_and_recompile(tmp_path, docs).machine("MachineDoc:m1")
    assert md1.content_hash != md2.content_hash


def test_hash_cambia_con_event_schema(tmp_path: Path) -> None:
    md1 = _decl(tmp_path).machine("MachineDoc:m1")
    docs = default_docs()
    for i, (model, name, fields) in enumerate(docs):
        if model == "EventTypeDoc":
            docs[i] = (model, name, {**fields, "payload_schema": {"type": "object", "required": ["x"]}})
    md2 = _edit_and_recompile(tmp_path, docs).machine("MachineDoc:m1")
    assert md1.content_hash != md2.content_hash


def test_invalid_cardinality_machine(tmp_path: Path) -> None:
    docs = default_docs()
    hd = docs[0]
    docs[0] = (hd[0], hd[1], {**hd[2], "cardinality": "bogus"})
    decl = _edit_and_recompile(tmp_path, docs)
    with pytest.raises(GraphCompileError):
        decl.machine("MachineDoc:m1")


def test_machine_sin_estados_rechaza(tmp_path: Path) -> None:
    """Sin aristas has_state reales la máquina no compila (los refs no bastan)."""
    edges = [e for e in default_edges() if e[0] != "has_state"]
    ms = build_machine_store(tmp_path, edges=edges)
    decl = SldbDeclarations(KnowledgeBase.open(ms.root), store=ms.store)
    with pytest.raises(GraphCompileError):
        decl.machine("MachineDoc:m1")


def test_transition_a_estado_ajeno_rechaza(tmp_path: Path) -> None:
    """Una transición que apunta a un estado fuera de has_state es endpoint inválido."""
    docs = default_docs()
    for i, (model, name, fields) in enumerate(docs):
        if model == "TransitionDoc":
            docs[i] = (model, name, {**fields, "target_ref": "StateDoc:st-99"})
    decl = _edit_and_recompile(tmp_path, docs)
    with pytest.raises(GraphCompileError):
        decl.machine("MachineDoc:m1")


def test_estado_inicial_miembro_de_has_state(tmp_path: Path) -> None:
    docs = default_docs()
    hd = docs[0]
    docs[0] = (hd[0], hd[1], {**hd[2], "initial_state_ref": "StateDoc:st-99"})
    decl = _edit_and_recompile(tmp_path, docs)
    with pytest.raises(GraphCompileError):
        decl.machine("MachineDoc:m1")


def test_event_type_schema_tipado_invalido_no_entra(tmp_path: Path) -> None:
    """Payload schema mal tipado (lista) es rechazado en el ingreso: no llega al compilador."""
    docs = default_docs()
    for i, (model, name, fields) in enumerate(docs):
        if model == "EventTypeDoc":
            docs[i] = (model, name, {**fields, "payload_schema": [1, 2, 3]})
    with pytest.raises(ValidationError):  # pydantic/sldb rechaza en create_document
        build_machine_store(tmp_path, docs=docs)


def test_guard_expression_invalido_no_entra(tmp_path: Path) -> None:
    """Un guard con expression mal tipado es rechazado en el ingreso (fail-closed)."""
    docs: list[tuple[str, str, dict[str, object]]] = [
        *default_docs(),
        ("GuardDoc", "g1.md", {"id": "g1", "title": "g1", "machine_ref": "MachineDoc:m1", "expression": []}),
    ]
    for i, (model, name, fields) in enumerate(docs):
        if model == "TransitionDoc":
            docs[i] = (model, name, {**fields, "guard_refs": ["GuardDoc:g1"]})
    with pytest.raises(ValidationError):
        build_machine_store(tmp_path, docs=docs, edges=default_edges())


def test_compiler_rechaza_grafo_incompleto(tmp_path: Path) -> None:
    """El compilador rechaza un grafo neutral sin pertenencia real (fail-closed)."""
    from cognitive import (
        EventTypeGraphDoc,
        MachineGraph,
        MachineGraphDoc,
        StateGraphDoc,
        TransitionGraphDoc,
    )
    from kb.machines import GraphCompiler
    from ontology import Ref

    def r(key: str) -> Ref:
        return Ref(kind="kb", id=key)

    machine = MachineGraphDoc(
        id="m1",
        title="M1",
        version="1",
        family="consent",
        initial_state_ref=r("StateDoc:st-1"),
        state_refs=(r("StateDoc:st-1"), r("StateDoc:st-2")),
        transition_refs=(r("TransitionDoc:t1"),),
        event_type_refs=(r("EventTypeDoc:ev-app"),),
    )
    state1 = StateGraphDoc(id="st-1", machine_ref=r("MachineDoc:m1"))
    state2 = StateGraphDoc(id="st-2", machine_ref=r("MachineDoc:m1"), terminal=True)
    event = EventTypeGraphDoc(
        id="ev-app",
        machine_ref=r("MachineDoc:m1"),
        name="approve",
        payload_schema={"type": "object"},
    )
    transition = TransitionGraphDoc(
        id="t1",
        machine_ref=r("MachineDoc:m1"),
        source_ref=r("StateDoc:st-1"),
        target_ref=r("StateDoc:st-2"),
        event_type_ref=r("EventTypeDoc:ev-app"),
    )
    compiler = GraphCompiler()
    # Sin aristas has_state reales (edges vacías) ⇒ pertenencia falla ⇒ error.
    graph = MachineGraph(
        machine=machine,
        states=(state1, state2),
        transitions=(transition,),
        events=(event,),
        guards=(),
        edges=(),
    )
    with pytest.raises(GraphCompileError):
        compiler.compile(graph)


def test_hash_content_une_a_instancia_fijada(tmp_path: Path) -> None:
    """Editar el grafo cambia el content_hash: una instancia fijada a una versión vieja no mutea."""
    ms = build_machine_store(tmp_path)
    decl = SldbDeclarations(KnowledgeBase.open(ms.root), store=ms.store)
    md_old = decl.machine("MachineDoc:m1")
    old_hash = md_old.content_hash

    docs = default_docs()
    for i, (model, name, fields) in enumerate(docs):
        if model == "TransitionDoc":
            docs[i] = (model, name, {**fields, "priority": 5})
    ms2 = build_machine_store(tmp_path / "v2", docs=docs)
    decl2 = SldbDeclarations(KnowledgeBase.open(ms2.root), store=ms2.store)
    md_new = decl2.machine("MachineDoc:m1")
    assert md_new.content_hash != old_hash


def test_pinned_ref_and_common_hash(tmp_path: Path) -> None:
    from cognitive import machine_definition_hash
    from ontology import Ref

    unbound = _decl(tmp_path)
    source = unbound._kb  # pyright: ignore[reportPrivateUsage]
    declarations = SldbDeclarations(source, bound_release_id="r1", verified_fingerprint=source.fingerprint)
    for ref in ("kb:MachineDoc:m1@r1", "MachineDoc:m1@r1", Ref.parse("kb:MachineDoc:m1@r1")):
        definition = declarations.machine(ref)
        assert definition.ref == Ref.parse("kb:MachineDoc:m1@r1")
        assert definition.content_hash == machine_definition_hash(definition)
        assert declarations.resolve(ref).key == "MachineDoc:m1"
    assert declarations.machine("m1").ref == Ref.parse("kb:MachineDoc:m1@r1")


def test_assignments_and_variables_schema_roundtrip(tmp_path: Path) -> None:
    from cognitive import machine_definition_hash

    docs = default_docs()
    for i, (model, name, fields) in enumerate(docs):
        if model == "MachineDoc":
            docs[i] = (
                model,
                name,
                {**fields, "variables_schema": {"type": "object", "properties": {"x": {"type": "null"}}}},
            )
        if model == "TransitionDoc":
            docs[i] = (model, name, {**fields, "assignments": {"x": {"literal": None}}})
    definition = _edit_and_recompile(tmp_path, docs).machine("MachineDoc:m1")
    assert definition.variables_schema["properties"] == {"x": {"type": "null"}}
    assert definition.transitions[0].assignments["x"].literal is None
    assert definition.transitions[0].assignments["x"].model_fields_set == {"literal"}
    assert definition.content_hash == machine_definition_hash(definition)


@pytest.mark.parametrize("binding", [{}, {"literal": None, "snapshot_path": ["event", "payload"]}])
def test_assignment_exactly_one_rejected(tmp_path: Path, binding: dict[str, object]) -> None:
    docs = default_docs()
    for i, (model, name, fields) in enumerate(docs):
        if model == "TransitionDoc":
            docs[i] = (model, name, {**fields, "assignments": {"x": binding}})
    with pytest.raises(GraphCompileError):
        _edit_and_recompile(tmp_path, docs).machine("MachineDoc:m1")


@pytest.mark.parametrize("priority", [True, "1"])
def test_loader_rejects_priority_coercion(tmp_path: Path, priority: object) -> None:
    from kb.machines import SldbGraphLoader

    store = build_machine_store(tmp_path)
    documents = KnowledgeBase.open(store.root).documents()
    authored = [
        document.model_copy(update={"payload": {**document.payload, "priority": priority}})
        if document.model == "TransitionDoc"
        else document
        for document in documents
    ]
    with pytest.raises(GraphCompileError, match="entero"):
        SldbGraphLoader(store.store).load(authored, "MachineDoc:m1")


def test_unknown_release_cannot_relabel_current_source(tmp_path: Path) -> None:
    unbound = _decl(tmp_path)
    with pytest.raises(GraphCompileError, match="verified source binding"):
        unbound.machine("kb:MachineDoc:m1@r2")
    source = unbound._kb  # pyright: ignore[reportPrivateUsage]
    bound = SldbDeclarations(source, bound_release_id="r1", verified_fingerprint=source.fingerprint)
    assert bound.machine("kb:MachineDoc:m1@r1").ref.release_id == "r1"
    with pytest.raises(GraphCompileError, match="verified source binding"):
        bound.machine("kb:MachineDoc:m1@r2")


def test_release_binding_requires_matching_verified_fingerprint(tmp_path: Path) -> None:
    source = _decl(tmp_path)._kb  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(ValueError, match="fingerprint differs"):
        SldbDeclarations(source, bound_release_id="r1", verified_fingerprint="unrelated-fingerprint")


def test_state_cannot_have_second_graph_owner(tmp_path: Path) -> None:
    docs = default_docs()
    docs.append(
        (
            "MachineDoc",
            "m2.md",
            {
                "id": "m2",
                "title": "M2",
                "version": "1.0",
                "family": "consent",
                "initial_state_ref": "StateDoc:st-1",
                "state_refs": ["StateDoc:st-1"],
            },
        )
    )
    edges = [*default_edges(), ("has_state", "MachineDoc:m2", "StateDoc:st-1")]
    store = build_machine_store(tmp_path, docs=docs, edges=edges)
    knowledge, report = KnowledgeBase.open_lenient(store.root)
    assert not report.is_valid
    declarations = SldbDeclarations(knowledge, store=store.store)
    with pytest.raises(GraphCompileError, match="exactly one graph owner"):
        declarations.machine("MachineDoc:m1")
