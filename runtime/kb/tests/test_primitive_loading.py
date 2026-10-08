"""Carga de primitivas del grafo de máquina desde SLDB real (canonical §03).

Usa `machine_fixture` para montar un store `.sldb` REAL (init_store → add_model →
create_document → rebuild_edges) y verifica que `KnowledgeBase` + `SldbDeclarations`
cargan documentos, huellas y la definición compilada de una máquina.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from machine_fixture import build_machine_store

from kb import KnowledgeBase
from kb.declarations import SldbDeclarations
from kb.machines import GraphCompileError


@pytest.fixture
def decl(tmp_path: Path) -> SldbDeclarations:
    ms = build_machine_store(tmp_path)
    return SldbDeclarations(KnowledgeBase.open(ms.root), store=ms.store)


def test_typed_edges_are_real(tmp_path: Path) -> None:
    """Las aristas tipadas has_state se leen del índice real de SLDB, no de refs."""
    ms = build_machine_store(tmp_path)
    assert ms.store.is_dir()
    from sldb.api.edges.edge_reading import edges_from

    typed = edges_from(ms.store, "MachineDoc:m1", relation="has_state", include_linked=False)
    assert len(typed) == 2


def test_primitive_roundtrip(decl: SldbDeclarations) -> None:
    doc = decl.resolve("MachineDoc:m1")
    assert doc.model == "MachineDoc"
    assert doc.payload["initial_state_ref"] == "StateDoc:st-1"
    assert doc.key == "MachineDoc:m1"


def test_resolve_short_name(decl: SldbDeclarations) -> None:
    assert decl.resolve("MachineDoc:m1").name == "m1"
    assert decl.resolve("m1").key == "MachineDoc:m1"


def test_fingerprint_es_raiz_merkle(decl: SldbDeclarations) -> None:
    assert len(decl.fingerprint()) == 64


def test_machine_compiled(decl: SldbDeclarations) -> None:
    md = decl.machine("MachineDoc:m1")
    assert md.initial_state == "st-1"
    assert {s.id for s in md.states} == {"st-1", "st-2"}
    assert {t.id for t in md.transitions} == {"t1"}
    assert list(md.event_schemas) == ["approve"]
    assert md.content_hash
    assert len(md.content_hash) == 64


def test_machine_resolve_missing_raises(decl: SldbDeclarations) -> None:
    with pytest.raises(GraphCompileError):
        decl.machine("MachineDoc:nope")


def test_machine_hard_rejects_no_store(tmp_path: Path) -> None:
    """Sin store de grafo no hay máquina: refs authored por sí solos no bastan."""
    from kb.machines import SldbGraphLoader

    loader = SldbGraphLoader(tmp_path / "no-store")
    with pytest.raises(GraphCompileError):
        loader.load([], "MachineDoc:m1")
