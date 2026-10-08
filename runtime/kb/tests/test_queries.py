from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from kb import KnowledgeBase
from kb.rendering.materialize import strip_frontmatter
from kb.tags import is_blocked, is_under
from make_fixture import Doc, KbSpec, minimal


def test_by_model_incluye_subclases(minimal_kb: KnowledgeBase) -> None:
    assert [d.key for d in minimal_kb.by_model("Note")] == ["Note:nota-a", "SpecialNote:nota-b"]
    assert [d.key for d in minimal_kb.by_model("Note", include_subclasses=False)] == ["Note:nota-a"]


def test_by_tag_con_descendientes(minimal_kb: KnowledgeBase) -> None:
    assert [d.key for d in minimal_kb.by_tag("type.knowledge")] == [
        "Note:nota-a",
        "SpecialNote:nota-b",
        "Tool:tool-x",
    ]
    assert minimal_kb.by_tag("type.knowledge", include_descendants=False) == []
    assert [d.key for d in minimal_kb.by_tag("topic:uno")] == ["Note:nota-a"]


def test_by_tag_rechaza_formas_invalidas(minimal_kb: KnowledgeBase) -> None:
    with pytest.raises(ValueError, match="tag inválido"):
        minimal_kb.by_tag("Con Espacios")


def test_by_family(minimal_kb: KnowledgeBase) -> None:
    assert [d.key for d in minimal_kb.by_family("self")] == ["Tool:tool-x"]
    assert minimal_kb.by_family("") == []


def test_get_por_referencia_nombre_o_ref(minimal_kb: KnowledgeBase) -> None:
    by_key = minimal_kb.get("Note:nota-a")

    assert minimal_kb.get("nota-a") == by_key
    assert minimal_kb.get("kb:Note:nota-a") == by_key
    assert by_key.ancestors == []
    assert minimal_kb.get("nota-b").ancestors == ["Note"]
    with pytest.raises(KeyError, match="ninguno"):
        minimal_kb.get("no-existe")


def test_relaciones(minimal_kb: KnowledgeBase) -> None:
    [relation] = minimal_kb.relations("cites")

    assert (relation.source_ref, relation.target_ref) == ("Note:nota-a", "SpecialNote:nota-b")
    assert minimal_kb.outgoing("nota-a") == [relation]
    assert minimal_kb.incoming("nota-b", "cites") == [relation]
    assert minimal_kb.incoming("nota-a") == []
    with pytest.raises(KeyError):
        minimal_kb.relations("no_declarada")


def test_tipos_de_relacion_marcan_los_estructurales(minimal_kb: KnowledgeBase) -> None:
    types = {info.name: info.builtin for info in minimal_kb.relation_types()}

    assert types["cites"] is False
    assert types["has_document"] is True
    assert ("Note:nota-a" in {r.target_ref for r in minimal_kb.relations("has_document")}) is True


def test_elegibilidad_por_segmentos() -> None:
    assert is_under("status:proposed.v2", "status:proposed")
    assert not is_under("status:proposedx", "status:proposed")
    assert is_blocked(["a", "status:deprecated"], ["status:deprecated"])


def test_documentos_bloqueados_no_son_elegibles(build_kb: Callable[[KbSpec], Path]) -> None:
    spec = minimal()
    spec.docs.append(
        Doc(
            "Note",
            "notes/vieja.md",
            {"id": "vieja", "title": "v", "tags": ["status:deprecated"], "body": "x"},
        )
    )
    kb = KnowledgeBase.open(build_kb(spec))

    assert "Note:vieja" not in {d.key for d in kb.eligible()}
    assert kb.get("vieja").eligible is False
    assert kb.stats().eligible == kb.stats().documents - 1


def test_materializacion_ordenada_y_sin_frontmatter(minimal_kb: KnowledgeBase) -> None:
    text = minimal_kb.materialize()

    assert text == minimal_kb.materialize()
    assert text.startswith("# BASE DE CONOCIMIENTO (3 documentos)\n\n## notes\n\n### Note:nota-a\n\n# Nota A")
    assert text.index("## notes") < text.index("## self")
    assert "id: nota-a" not in text
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_render_es_el_de_sldb(minimal_kb: KnowledgeBase) -> None:
    assert minimal_kb.render("nota-a").startswith("---\nid: nota-a\n")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("---\na: 1\n---\ncuerpo\n---\n", "cuerpo\n---\n"),
        ("---\nsin cierre\n", "---\nsin cierre\n"),
        ("cuerpo\n---\nx\n---\n", "cuerpo\n---\nx\n---\n"),
    ],
)
def test_corte_del_frontmatter(text: str, expected: str) -> None:
    assert strip_frontmatter(text) == expected


def test_stats(minimal_kb: KnowledgeBase) -> None:
    stats = minimal_kb.stats()

    assert (stats.documents, stats.by_family, stats.relations_by_type) == (
        3,
        {"notes": 2, "self": 1},
        {"cites": 1},
    )
    assert stats.by_model["Trait"] == 0
