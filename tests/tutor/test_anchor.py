"""Esquema de la fuente (tabla de contenidos → fragmentos) y anclaje de átomos con `FakeJevClient`, en una
KB temporal con fragmentos de prueba; la cobertura de las ramas se deriva de lo anclado."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from kb_models.ingest import OutlineEntry
from kb_models.provenance import Provenance, parse_provenance_prose

from tutor import anchor, authoring, branches, ingest, outline, world
from tutor.authoring import KbWriter
from tutor.selector_jev import FakeJevClient

KB = "libro"
BRANCH = "branch-mecanismos"
#: Un «libro» mínimo: prefacio, tabla de contenidos con páginas impresas, dos capítulos con secciones.
BOOK = """Preface

This small book is a test fixture.

Contents
1 Introduction .......................................... 1
2 Mechanisms ............................................. 3
2.1 Interiorization . . . . . . . . . . . . . . . . . . . . . . . . . . . . 3
2.2 Encapsulation and Objects ............................ 4
References ............................................... 9

Chapter 1
Introduction
APOS Theory is a theory of how mathematical concepts can be learned. It describes Actions, Processes, Objects and Schemas.

Chapter 2
Mechanisms
2.1 Interiorization
Interiorization is the mechanism by which an Action is transformed into a Process: the individual can imagine the steps without performing them.

2.2 Encapsulation and Objects
Encapsulation occurs when the individual becomes aware of a Process as a totality and can apply transformations to it. The Process is encapsulated into a cognitive Object. Thematization is a different mechanism that applies to Schemas.

References
Arnon, I. (2014). APOS Theory.
"""
PAGE_OFFSETS = [(0, 1), (BOOK.index("Contents"), 2), (BOOK.index("Chapter 1"), 3), (BOOK.index("Chapter 2"), 4), (BOOK.index("2.2 Encapsulation and Objects\nEncapsulation occurs"), 5), (BOOK.index("References\nArnon"), 6)]


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("kbs")
    authoring.create_kb(KB, "Libro de prueba", root=base)
    authoring.upsert_branch(KB, {"id": BRANCH, "title": "Mecanismos", "parent": f"branch-{KB}", "summary": "Cómo se construyen las estructuras."}, root=base)
    authoring.upsert_branch(KB, {"id": "branch-vacia", "title": "Vacía", "parent": f"branch-{KB}", "summary": "Sin átomos."}, root=base)
    ingest.ingest_text(KB, "Libro", BOOK, chunk_chars=260, page_offsets=PAGE_OFFSETS, root=base)
    prov = [p.model_dump(mode="json") for p in parse_provenance_prose("Fuente principal: Capítulo 2, sección 2.2, del libro de Arnon et al. (2014), extraído desde `x.pdf`.")]
    for p in prov:
        p["source"] = "source-libro"
    authoring.upsert_atom(KB, {"id": "atom-encapsulacion", "title": "La encapsulación convierte un proceso en objeto", "question": "what", "answer": "Encapsulation occurs when the individual becomes aware of a Process as a totality: the Process is encapsulated into a cognitive Object.", "provenance": prov, "tags": ["topic:encapsulation", f"system:{KB}"], "parent": BRANCH}, root=base)
    lost = [{**p, "sections": ["2.1"]} for p in prov]
    authoring.upsert_atom(KB, {"id": "atom-sin-respaldo", "title": "Afirmación sin respaldo", "question": "what", "answer": "Los números primos son infinitos y la hipótesis de Riemann sigue abierta.", "provenance": lost, "tags": ["topic:primes", f"system:{KB}"], "parent": BRANCH}, root=base)
    authoring.upsert_atom(KB, {"id": "atom-experto", "title": "Dicho por un experto", "question": "what", "answer": "Un comentario de curación.", "provenance": "Conversacion de curacion con experto, 2026-07-16.", "tags": ["topic:curation", f"system:{KB}"], "parent": BRANCH}, root=base)
    return base


# -- esquema ------------------------------------------------------------------------------------


def test_parse_contents_handles_spaced_pages_and_ambiguity() -> None:
    entries = outline.parse_contents("1 Introduction ........ 1\n2 From Piaget ....... 5\n2.1 Reflective . . . . 6\n3 Mental Structures ......... 1 7\n3.1 Preliminary .... 17\nReferences ....... 2 2 7\nAbout the Authors ..... 2 3 3")
    assert [(e["number"], e["printed_page"], e["level"]) for e in entries] == [("1", 1, 0), ("2", 5, 0), ("2.1", 6, 1), ("3", 17, 0), ("3.1", 17, 1), ("References", 227, 0), ("About the Authors", 233, 0)]


def test_outline_locates_headings_and_pages(root: Path) -> None:
    writer = KbWriter.open(KB, root)
    data = outline.ensure_outline(writer, "source-libro")
    assert data is not None and data["id"] == "toc-source-libro" and (root / KB / "ingest" / "toc-source-libro.md").is_file()
    by_number = {e["number"]: e for e in data["entries"]}
    assert {"Prefacio", "Tabla de contenidos", "1", "2", "2.1", "2.2", "References"} <= set(by_number)
    assert by_number["1"]["found"] and by_number["2"]["found"] and by_number["2.2"]["found"]
    assert by_number["1"]["page_start"] == 3 and by_number["2"]["page_start"] == 4 and by_number["2.2"]["page_start"] == 5
    assert by_number["2.1"]["chunk_end"] < by_number["2.2"]["chunk_start"] <= by_number["2.2"]["chunk_end"]
    assert by_number["2"]["chunk_end"] >= by_number["2.2"]["chunk_end"]
    assert data["page_offset"] == 2
    spans, missing = outline.span_for(data, Provenance(kind="book", chapter=2, sections=["2.2"]))
    assert spans == [(by_number["2.2"]["chunk_start"], by_number["2.2"]["chunk_end"])] and missing == []
    spans, missing = outline.span_for(data, Provenance(kind="book", chapter=2, sections=["2.9"]))
    assert missing == ["2.9"] and spans == [(by_number["2"]["chunk_start"], by_number["2"]["chunk_end"])]
    assert outline.span_for(data, Provenance(kind="book", sections=["Introducción"]))[0] == [(by_number["1"]["chunk_start"], by_number["1"]["chunk_end"])]
    again = outline.ensure_outline(writer, "source-libro")  # idempotente: reutiliza el documento (sldb omite los None al leer)
    assert [OutlineEntry.model_validate(e) for e in again["entries"]] == [OutlineEntry.model_validate(e) for e in data["entries"]]


# -- anclaje ------------------------------------------------------------------------------------------


def test_anchor_kb_with_fake_jev_and_cache(root: Path) -> None:
    client = FakeJevClient()
    report = anchor.anchor_kb(KB, root, client=client, top_k=3)
    assert report["n_atoms"] == 3 and report["anchored"] == 1 and report["unanchored"] == 1 and report["skipped"] == 1
    assert report["unanchored_ids"] == ["atom-sin-respaldo"] and report["jev_calls"] > 0 and report["cached"] == 0
    assert report["nouls"]["n"] == report["jev_calls"] and sum(report["nouls"]["buckets"].values()) == report["nouls"]["n"]
    kb = KbWriter.open(KB, root).kb()
    atom = world.get_atom(kb, "atom-encapsulacion")
    [ref] = atom["provenance_refs"]
    assert ref["anchored"] is True and 1 <= len(ref["chunk_ids"]) <= 3 and ref["pages"] == [5, 5]
    assert all(n >= 0.5 for n in ref["nouls"]) and ref["nouls"] == sorted(ref["nouls"], reverse=True)
    assert ref["excerpt"] and "encapsulation" in ref["excerpt"].lower() and ref["excerpt"] in BOOK.replace("\n", " ")
    assert atom["provenance"].startswith("Arnon et al. (2014), cap. 2 §2.2, p. 5") if ref["source"] == "source-arnon-et-al-2014-apos-theory" else atom["provenance"].startswith("source-libro, cap. 2 §2.2, p. 5")
    assert atom["citation"].endswith(f"«{ref['excerpt']}»") and atom["surface_url"] == "/surface?atom=atom-encapsulacion"
    lost = world.get_atom(kb, "atom-sin-respaldo")
    assert lost["provenance_refs"][0]["anchored"] is False and lost["provenance_refs"][0]["chunk_ids"] == [] and lost["surface_url"] is None
    expert = world.get_atom(kb, "atom-experto")
    assert expert["provenance_refs"][0]["kind"] == "expert" and expert["provenance_refs"][0].get("anchored") is None
    # el texto del átomo en disco se renderiza desde la procedencia: página real y cita
    text = (root / KB / "knowledge" / "atom-encapsulacion.md").read_text(encoding="utf-8")
    assert "## Procedencia\n\n" in text and "p. 5" in text and re.search(r"chunk_ids:\n\s*- source-libro-chunk-", text)
    # segunda pasada: todo sale de la caché, sin llamar a Jev
    calls = len(client.calls)
    again = anchor.anchor_kb(KB, root, client=client, top_k=3)
    assert again["jev_calls"] == 0 and again["cached"] == 2 and len(client.calls) == calls and again["written"] == 0
    assert (root / KB / ".cache" / anchor.CACHE_FILE).is_file()


def test_branch_coverage_derived_from_descendants(root: Path) -> None:
    writer = KbWriter.open(KB, root)
    data = outline.load_outline(writer.kb(), "source-libro")
    changed = branches.apply_coverage(writer, data)
    assert changed >= 2
    kb = writer.kb()
    mecanismos = world.get_atom(kb, BRANCH)
    cov = mecanismos["coverage"]
    assert cov["n_atoms"] == 3 and cov["n_expert"] == 1 and cov["n_unanchored"] == 1 and cov["chapters"] == [2]
    assert cov["sections"] == ["2.1", "2.2"] and cov["pages"][0] <= 5 <= cov["pages"][1] and len(cov["chunk_ids"]) >= 1
    assert mecanismos["provenance"].startswith("Cubre source-libro cap. 2, §2.1, 2.2") and "3 átomos (1 de conversación con experto, 1 sin anclaje en la fuente)" in mecanismos["provenance"]
    assert mecanismos["surface_url"].startswith("/surface?page=")
    assert world.get_atom(kb, "branch-vacia")["provenance"] == "Rama sin átomos todavía."
    root_branch = world.get_atom(kb, f"branch-{KB}")
    assert root_branch["coverage"]["n_atoms"] == 3
    assert branches.apply_coverage(writer, data) == 0  # idempotente


def test_rebuild_keeps_anchors(root: Path) -> None:
    result = authoring.rebuild_kb(KB, root)
    assert result["ok"] and result["tracked"].get("SourceOutline") == 1
    assert world.get_atom(KbWriter.open(KB, root).kb(), "atom-encapsulacion")["provenance_refs"][0]["chunk_ids"]
