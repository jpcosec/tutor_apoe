"""Una KB negativa por regla (spec 01 §8.1): cada una dispara su regla."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from kb import KnowledgeBase, KnowledgeBaseInvalid, KnowledgeBaseNotFound
from make_fixture import Doc, KbSpec, minimal, relation, relation_doc

Builder = Callable[[KbSpec], Path]


def rules_of(root: Path) -> set[str]:
    return KnowledgeBase.open_lenient(root)[1].rules()


def with_docs(*docs: Doc, **manifest: object) -> KbSpec:
    spec = minimal()
    spec.docs.extend(docs)
    spec.manifest.update(manifest)
    return spec


def note(name: str, **fields: object) -> Doc:
    return Doc("Note", f"notes/{name}.md", {"id": name, "title": name, "tags": [], "body": "x", **fields})


@pytest.mark.spec("01-V0")
@pytest.mark.parametrize(
    "manifest",
    [
        {"kb": {"name": "x", "kb_version": 1, "models": "minimal_models", "desconocida": 1}},
        {"kb": {"name": "Mayus", "kb_version": 1, "models": "minimal_models"}},
        {"kb": {"kb_version": 2, "models": "minimal_models"}},
        {"otra": {}},
    ],
)
def test_v0_manifiesto_invalido_bloquea(build_kb: Builder, manifest: dict[str, object]) -> None:
    root = build_kb(minimal())
    (root / "kb.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")

    with pytest.raises(KnowledgeBaseInvalid) as invalid:
        KnowledgeBase.open_lenient(root)

    assert invalid.value.report.rules() == {"V0"}


@pytest.mark.spec("01-V0")
def test_v0_yaml_roto_y_sin_manifiesto(build_kb: Builder, tmp_path: Path) -> None:
    root = build_kb(minimal())
    (root / "kb.yaml").write_text("kb: [", encoding="utf-8")

    with pytest.raises(KnowledgeBaseInvalid):
        KnowledgeBase.open(root)
    with pytest.raises(KnowledgeBaseNotFound):
        KnowledgeBase.open(tmp_path / "vacia")


@pytest.mark.spec("01-V1")
def test_v1_modelo_fuera_del_paquete_declarado(build_kb: Builder) -> None:
    root = build_kb(minimal())
    manifest = yaml.safe_load((root / "kb.yaml").read_text())
    manifest["kb"]["models"] = "otro_paquete"
    (root / "kb.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")

    assert rules_of(root) == {"V1"}


@pytest.mark.spec("01-V1")
def test_v1_modelo_no_importable_bloquea(build_kb: Builder) -> None:
    root = build_kb(minimal())
    index = root / ".sldb" / "core" / "store_index.yaml"
    index.write_text(index.read_text().replace("minimal_models:Tool\n", "minimal_models:NoExiste\n"))

    with pytest.raises(KnowledgeBaseInvalid) as invalid:
        KnowledgeBase.open_lenient(root)

    assert invalid.value.report.rules() == {"V1"}


@pytest.mark.spec("01-V1")
def test_v1_sin_store_bloquea(build_kb: Builder) -> None:
    root = build_kb(minimal())
    (root / ".sldb").rename(root / "otro")

    with pytest.raises(KnowledgeBaseInvalid) as invalid:
        KnowledgeBase.open_lenient(root)

    assert invalid.value.report.rules() == {"V1"}


@pytest.mark.spec("01-V1")
def test_v1_store_desalineado(build_kb: Builder) -> None:
    root = build_kb(minimal())
    path = root / "notes" / "nota-a.md"
    path.write_text(path.read_text().replace("A.", "A modificada."))

    assert rules_of(root) == {"V1"}


@pytest.mark.spec("01-V2")
def test_v2_id_distinto_del_nombre(build_kb: Builder) -> None:
    assert rules_of(build_kb(with_docs(note("nota-c", id="otro-id")))) == {"V2"}


@pytest.mark.spec("01-V3")
def test_v3_nombre_repetido_entre_modelos(build_kb: Builder) -> None:
    tool = Doc("Tool", "self/nota-a.md", {"id": "nota-a", "title": "t", "parameters": '{"name": "y"}'})

    assert rules_of(build_kb(with_docs(tool))) == {"V3"}


@pytest.mark.spec("01-V4")
@pytest.mark.parametrize("tag", ["Mal Tag", "type.reservado", "ns:"])
def test_v4_tag_editorial_invalido(build_kb: Builder, tag: str) -> None:
    assert rules_of(build_kb(with_docs(note("nota-c", tags=[tag])))) == {"V4"}


def category(name: str, tag: str, parent: str | None = None) -> Doc:
    fields: dict[str, object] = {"id": name, "title": name, "tag": tag, "meaning": "m"}
    if parent is not None:
        fields["parent"] = parent
    return Doc("Category", f"kb/categories/{name}.md", fields)


@pytest.mark.spec("01-V5")
def test_v5_tag_sin_categoria_y_padre_huerfano(build_kb: Builder) -> None:
    spec = with_docs(category("category-topic", "topic", parent="inexistente"), categories="required")

    report = KnowledgeBase.open_lenient(build_kb(spec))[1]

    assert report.rules() == {"V5"}
    assert {e.message for e in report.errors} == {"parent 'inexistente' no es el tag de otra categoría"}


@pytest.mark.spec("01-V5")
def test_v5_categorias_requeridas_sin_categoria(build_kb: Builder) -> None:
    assert rules_of(build_kb(with_docs(categories="required"))) == {"V5"}


def test_v5_categorias_completas_pasan(build_kb: Builder) -> None:
    spec = with_docs(category("category-topic", "topic"), categories="required")

    assert rules_of(build_kb(spec)) == set()


@pytest.mark.spec("01-V6")
def test_v6_arista_a_documento_inexistente(build_kb: Builder) -> None:
    edge = relation_doc("Note:nota-a", "Note:no-existe")

    assert "V6" in rules_of(build_kb(with_docs(edge)))


def reference(expect: dict[str, object]) -> Doc:
    turns = [{"who": "user", "text": "hola"}, {"who": "agent", "text": "hola", "expect": expect}]
    return Doc(
        "Reference", "kb/references/ref-a.md", {"id": "ref-a", "title": "r", "turns": turns, "purpose": "p"}
    )


@pytest.mark.spec("01-V7")
def test_v7_expect_cita_documento_inexistente(build_kb: Builder) -> None:
    assert rules_of(build_kb(with_docs(reference({"step": "Note:no-existe"})))) == {"V7"}


def test_v7_expect_por_ancestro_resuelve(build_kb: Builder) -> None:
    assert rules_of(build_kb(with_docs(reference({"step": "Note:nota-b", "tool": "hacer_x"})))) == set()


@pytest.mark.spec("01-V8")
def test_v8_referencia_con_modelo_que_no_es_ancestro(build_kb: Builder) -> None:
    edge = relation_doc("SpecialNote:nota-a", "Note:nota-a")

    assert "V8" in rules_of(build_kb(with_docs(edge)))


@pytest.mark.spec("01-V9")
def test_v9_prueba_de_tool_no_declarada(build_kb: Builder) -> None:
    check = Doc(
        "ToolCheck",
        "kb/tool_tests/tt-a.md",
        {
            "id": "tt-a",
            "title": "t",
            "tool": "no_declarada",
            "args": {},
            "expect": {"status": "ok"},
            "purpose": "p",
        },
    )

    assert rules_of(build_kb(with_docs(check))) == {"V9"}


@pytest.mark.spec("01-V10", "13-I4")
@pytest.mark.parametrize("value", ["subject:4471", "record:factura:57", "turn:s-1:3"])
def test_v10_la_kb_no_apunta_a_datos(build_kb: Builder, value: str) -> None:
    assert rules_of(build_kb(with_docs(note("nota-c", body=value)))) == {"V10"}


def trait(name: str) -> Doc:
    return Doc("Trait", f"user/{name}.md", {"id": name, "title": name})


def style(name: str, applies_when: list[str] | None = None) -> Doc:
    fields: dict[str, object] = {"id": name, "title": name}
    if applies_when is not None:
        fields["applies_when"] = applies_when
    return Doc("Style", f"self/{name}.md", fields)


@pytest.mark.spec("01-V11")
@pytest.mark.parametrize("condition", ["tipo == grande", "profile.edad > 3", "trait:no-existe"])
def test_v11_condicion_invalida(build_kb: Builder, condition: str) -> None:
    spec = with_docs(trait("trait-edad"), style("style-general"), style("style-x", [condition]))

    assert rules_of(build_kb(spec)) == {"V11"}


def test_v11_condiciones_validas(build_kb: Builder) -> None:
    conditions = ["profile.tipo == grande", "profile.tramo in [a, b]", "trait:trait-edad"]
    spec = with_docs(trait("trait-edad"), style("style-general"), style("style-x", conditions))

    assert rules_of(build_kb(spec)) == set()


@pytest.mark.spec("01-V12")
def test_v12_dos_variantes_generales(build_kb: Builder) -> None:
    assert rules_of(build_kb(with_docs(style("style-a"), style("style-b")))) == {"V12"}


@pytest.mark.spec("01-V13")
def test_v13_nombre_fuera_de_la_norma_bloquea(build_kb: Builder) -> None:
    root = build_kb(
        with_docs(Doc("Note", "notes/Nota_C.md", {"id": "Nota_C", "title": "c", "tags": [], "body": "x"}))
    )

    with pytest.raises(KnowledgeBaseInvalid) as invalid:
        KnowledgeBase.open_lenient(root)

    assert invalid.value.report.rules() == {"V13"}


@pytest.mark.spec("01-V13")
def test_v13_relacion_con_nombre_que_no_sale_de_sus_extremos(build_kb: Builder) -> None:
    edge = Doc("RelationDoc", "relations/cita-rara.md", relation("Note:nota-a", "SpecialNote:nota-b"))

    assert rules_of(build_kb(with_docs(edge))) == {"V13"}


@pytest.mark.spec("01-V13")
def test_v13_extremo_sin_modelo(build_kb: Builder) -> None:
    edge = Doc(
        "RelationDoc", "relations/cites--nota-a--nota-b-bis.md", relation("nota-a", "SpecialNote:nota-b")
    )

    assert "V13" in rules_of(build_kb(with_docs(edge)))
