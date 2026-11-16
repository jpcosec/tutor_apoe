"""Procedencia estructurada: el parser cubre el 100% de los átomos fuente, la prosa se renderiza desde el
modelo (nunca al revés), la cobertura de las ramas se deriva de sus descendientes y ningún `.md` de la KB
ni de `desk/atoms/branches` lleva texto de build («Nodo de organización», «kb_build»)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from kb_models.apos import BranchNode, KnowledgeAtom
from kb_models.provenance import (
    Coverage,
    Provenance,
    ProvenanceKind,
    ProvenanceParseError,
    parse_provenance_prose,
    render_coverage,
    render_provenance,
)

from tutor import world
from tutor.kb_build import read_atoms

DESK = world.repo_root() / "desk" / "atoms"
BANNED = ("Nodo de organización", "kb_build", "Inferida por", "no existe como archivo")


def test_parser_covers_every_source_atom() -> None:
    atoms = [a for a in read_atoms(DESK) if a.node_type == "knowledge"]
    assert len(atoms) == 94
    failures = []
    for atom in atoms:
        try:
            items = parse_provenance_prose(atom.provenance_text, strict=True)
        except ProvenanceParseError as error:
            failures.append(f"{atom.id}: {error}")
            continue
        assert items, atom.id
        assert all(i.kind in (ProvenanceKind.BOOK, ProvenanceKind.EXPERT) for i in items), atom.id
    assert not failures, failures
    kinds = [i.kind for a in atoms for i in a.provenance]
    assert kinds.count(ProvenanceKind.EXPERT) == 4
    assert all(i.source == "source-arnon-et-al-2014-apos-theory" for a in atoms for i in a.provenance if i.kind == ProvenanceKind.BOOK)


@pytest.mark.parametrize(
    ("prose", "expected"),
    [
        ("Fuente principal: Capítulo 3, sección 3.2.1, del libro de Arnon et al. (2014), extraído desde `x.pdf`.", [(3, ["3.2.1"], None)]),
        ("Fuente principal: Capítulo 5, secciones 5.2.4 y 5.2.5, del libro de Arnon et al. (2014), extraído desde `x.pdf`.", [(5, ["5.2.4", "5.2.5"], None)]),
        ("Fuente principal: Capítulos 1, 8 y 9 del libro de Arnon et al. (2014), extraído desde `x.pdf`.", [(1, [], None), (8, [], None), (9, [], None)]),
        ("Fuente principal: Capítulo 3, sección 3.2.5, y Capítulo 7 del libro de Arnon et al. (2014), extraído desde `x.pdf`.", [(3, ["3.2.5"], None), (7, [], None)]),
        ("Fuente principal: Capítulo 1, presentación del Capítulo 9, del libro de Arnon et al. (2014), extraído desde `x.pdf`.", [(1, [], "presentación del Capítulo 9"), (9, [], None)]),
        ("Fuente principal: nota al pie y discusión de la sección 4.1 del Capítulo 4, del libro de Arnon et al. (2014), extraído desde `x.pdf`.", [(4, ["4.1"], "nota al pie y discusión de la sección 4.1 del Capítulo 4")]),
        ("Fuente principal: Capítulo 3, sección 3.2.4, especialmente el ejemplo de composición de funciones, del libro de Arnon et al. (2014), extraído desde `x.pdf`.", [(3, ["3.2.4"], "especialmente el ejemplo de composición de funciones")]),
    ],
)
def test_parser_variants(prose: str, expected: list[tuple[int, list[str], str | None]]) -> None:
    items = parse_provenance_prose(prose, strict=True)
    assert [(i.chapter, i.sections, i.note) for i in items] == expected


def test_parser_named_parts_and_expert() -> None:
    items = parse_provenance_prose("Fuente principal: prefacio, tabla de contenidos e introducción del libro de Arnon et al. (2014), extraído desde el PDF ubicado en `x.pdf`.", strict=True)
    assert [i.sections for i in items] == [["Prefacio"], ["Tabla de contenidos"], ["Introducción"]]
    assert render_provenance(items) == "Arnon et al. (2014), prefacio; tabla de contenidos; introducción."
    [expert] = parse_provenance_prose("Conversacion de curacion con experto, 2026-07-16.", strict=True)
    assert expert.kind == ProvenanceKind.EXPERT and expert.note == "2026-07-16"
    assert render_provenance([expert]) == "Conversación de curación con experto (2026-07-16)."
    with pytest.raises(ProvenanceParseError):
        parse_provenance_prose("lo dijo alguien", strict=True)
    assert parse_provenance_prose("lo dijo alguien")[0].kind == ProvenanceKind.DERIVED


def test_render_short_citation_with_pages_and_excerpt() -> None:
    item = Provenance(kind="book", source="source-arnon-et-al-2014-apos-theory", chapter=3, sections=["3.2.1"], pages=[23, 25], excerpt="An Action is a transformation.", chunk_ids=["c-1"], nouls=[0.9], anchored=True)
    assert render_provenance([item]) == "Arnon et al. (2014), cap. 3 §3.2.1, pp. 23–25."
    assert render_provenance([item], with_excerpt=True).endswith("«An Action is a transformation.»")
    assert render_provenance([item, item.model_copy(update={"chapter": 7, "sections": [], "pages": [117, 117]})]) == "Arnon et al. (2014), cap. 3 §3.2.1, pp. 23–25; cap. 7, p. 117."
    with pytest.raises(ValueError):
        Provenance(kind="book", pages=[5, 2])


def test_knowledge_atom_renders_citation_from_provenance() -> None:
    atom = KnowledgeAtom.model_validate({"id": "atom-x", "title": "X", "five_wh_one_plus": "what", "answer": "A.", "citation": "texto viejo que no manda", "provenance": [{"kind": "book", "source": "source-arnon-et-al-2014-apos-theory", "chapter": 2, "sections": ["2.1"]}]})
    assert atom.citation == "Arnon et al. (2014), cap. 2 §2.1."
    assert "⸢rev•citation⸥" in KnowledgeAtom.__template__ and "provenance: ⸢rev•provenance⸥" in KnowledgeAtom.__template__


def test_branch_renders_provenance_from_coverage() -> None:
    coverage = Coverage(sources=["source-arnon-et-al-2014-apos-theory"], chapters=[3], sections=["3.2", "3.3", "3.4", "3.5"], pages=[20, 41], chunk_ids=["c-1"], n_atoms=7, n_expert=1)
    assert render_coverage(coverage) == "Cubre Arnon et al. (2014) cap. 3, §3.2–3.5, pp. 20–41; 7 átomos (1 de conversación con experto)."
    branch = BranchNode.model_validate({"id": "branch-x", "title": "X", "description": "Qué abarca.", "coverage": coverage.model_dump(), "provenance": "ignorado"})
    assert branch.provenance.startswith("Cubre Arnon et al. (2014) cap. 3")
    assert render_coverage(Coverage(n_atoms=0)) == "Rama sin átomos todavía."


def test_kb_branches_have_real_descriptions_and_coverage(kb) -> None:
    branches = world.list_branches(kb)
    assert len(branches) == 59
    for branch in branches:
        assert branch["summary"] and not any(b in branch["summary"] for b in BANNED), branch["id"]
        assert branch["coverage"] is not None, branch["id"]
        assert branch["provenance"].startswith(("Cubre ", "Agrupa ", "Rama sin")), branch["id"]
    root = world.get_atom(kb, "branch-apos")
    assert root["coverage"]["n_atoms"] == 89 and root["coverage"]["chapters"][:3] == [1, 2, 3]
    encapsulation = world.get_atom(kb, "branch-apos-mechanisms-encapsulation")
    assert encapsulation["coverage"]["sections"] == ["3.2.3"] and encapsulation["coverage"]["n_atoms"] == 2
    assert encapsulation["provenance"].startswith("Cubre Arnon et al. (2014) cap. 3, §3.2.3")


def test_no_build_text_in_kb_or_desk_branches(kb_root: Path) -> None:
    offenders = []
    for folder in (kb_root / "knowledge", kb_root / "sources", kb_root / "taxonomy", DESK / "branches"):
        for path in folder.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            # El sello `sldb:` del frontmatter nombra al actor que escribió el documento; no es texto de la KB.
            text = re.sub(r"^sldb:\n(?:  .*\n)+", "", text, flags=re.M)
            if any(b in text for b in BANNED):
                offenders.append(str(path))
    assert not offenders, offenders
