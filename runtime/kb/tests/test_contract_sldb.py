"""Conductas de sldb de las que el módulo depende (spec 01 §8.1): si sldb cambia, esto falla primero."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sldb.api import check_edges, resolve_model_ref
from sldb.store.query import load_runtime_documents  # pyright: ignore[reportUnknownVariableType]

from make_fixture import FIXTURES, Doc, KbSpec, minimal, relation_doc, relation_type


def test_semantica_se_fusiona_por_mro(minimal_root: Path) -> None:
    docs = load_runtime_documents(minimal_root / ".sldb", resolve_model_ref, str(FIXTURES), False)
    special = next(d for d in docs if d.name == "nota-b")

    assert "type.knowledge.note" in special.semantic_tags  # heredado de Note


def test_c1_carga_omite_en_silencio_un_modelo_no_importable(build_kb: Callable[[KbSpec], Path]) -> None:
    root = build_kb(minimal())
    index = root / ".sldb" / "core" / "store_index.yaml"
    index.write_text(index.read_text().replace("minimal_models:Tool\n", "minimal_models:NoExiste\n"))

    docs = load_runtime_documents(root / ".sldb", resolve_model_ref, str(FIXTURES), False)

    assert "tool-x" not in {d.name for d in docs}  # sin error: por eso el módulo cuenta (C1)


def test_c4_check_edges_comprueba_cardinalidad(build_kb: Callable[[KbSpec], Path]) -> None:
    spec = minimal()
    one = {**relation_type("unico"), "cardinality": "one_to_one"}
    spec.docs += [
        Doc("RelationTypeDoc", "kgdb/relation_types/unico.md", one),
        relation_doc("Note:nota-a", "SpecialNote:nota-b", "unico"),
        relation_doc("Note:nota-a", "Note:nota-a", "unico"),
    ]

    report = check_edges(build_kb(spec) / ".sldb", include_linked=False)

    assert report.errors
