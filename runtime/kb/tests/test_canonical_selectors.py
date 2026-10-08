"""Selectores de conocimiento canónico: semántica KnowledgeSelector AND/OR, subtipos y lifecycle.

Usa la KB mínima de fixtures (`make_fixture`) con `Note` y su subclase `SpecialNote`, más
tags editoriales, para cubrir `SldbDeclarations.project`: subtipos registrados, tags_all
(AND), tags_any (OR), eligibility/lifecycle antes de seleccionar y orden estable por clave.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from cognitive import KnowledgeSelector
from kb import KnowledgeBase
from kb.declarations import SldbDeclarations
from make_fixture import Doc, KbSpec, build, minimal


def _decl(root: Path) -> SldbDeclarations:
    return SldbDeclarations(KnowledgeBase.open(root), store=root / ".sldb")


def _selector(
    *,
    models: tuple[str, ...] = (),
    tags_any: tuple[str, ...] = (),
    tags_all: tuple[str, ...] = (),
) -> KnowledgeSelector:
    return KnowledgeSelector(model_names=models, tags_any=tags_any, tags_all=tags_all)


def _default_spec() -> KbSpec:
    spec = minimal()
    spec.docs += [
        Doc(
            "Note",
            "notes/sobre-pago.md",
            {
                "id": "sobre-pago",
                "title": "Pago",
                "tags": ["topic:finanzas", "tipo:cobranza"],
                "body": "pago",
            },
        ),
        Doc(
            "Note",
            "notes/sobre-invoice.md",
            {"id": "sobre-invoice", "title": "Invoice", "tags": ["topic:finanzas"], "body": "invoice"},
        ),
        Doc(
            "SpecialNote",
            "notes/nota-especial-2.md",
            {
                "id": "nota-especial-2",
                "title": "Especial",
                "tags": ["topic:derecho"],
                "body": "especial",
                "level": 2,
            },
        ),
    ]
    return spec


def test_project_sin_selector_devuelve_por_clave(build_kb: Callable[[KbSpec], Path]) -> None:
    root = build_kb(_default_spec())
    decl = _decl(root)
    docs = decl.project()
    keys = [d.key for d in docs]
    assert keys == sorted(keys)  # orden estable por clave
    assert "Note:nota-a" in keys


def test_project_model_names_incluye_subtipos(build_kb: Callable[[KbSpec], Path]) -> None:
    root = build_kb(_default_spec())
    decl = _decl(root)
    docs = decl.project(_selector(models=("Note",)))
    models = {d.model for d in docs}
    assert models == {"Note", "SpecialNote"}


def test_project_tipo_concreto_no_expande_otra_rama(build_kb: Callable[[KbSpec], Path]) -> None:
    root = build_kb(_default_spec())
    decl = _decl(root)
    docs = decl.project(_selector(models=("SpecialNote",)))
    assert {d.model for d in docs} == {"SpecialNote"}


def test_tags_all_es_and(build_kb: Callable[[KbSpec], Path]) -> None:
    root = build_kb(_default_spec())
    decl = _decl(root)
    docs = decl.project(_selector(tags_all=("topic:finanzas", "tipo:cobranza")))
    assert [d.key for d in docs] == ["Note:sobre-pago"]


def test_tags_any_es_or(build_kb: Callable[[KbSpec], Path]) -> None:
    root = build_kb(_default_spec())
    decl = _decl(root)
    docs = decl.project(_selector(tags_any=("tipo:cobranza", "topic:derecho")))
    keys = {d.key for d in docs}
    assert "Note:sobre-pago" in keys
    assert "SpecialNote:nota-especial-2" in keys
    assert "Note:sobre-invoice" not in keys


def test_tags_all_and_any_combinados(build_kb: Callable[[KbSpec], Path]) -> None:
    root = build_kb(_default_spec())
    decl = _decl(root)
    docs = decl.project(_selector(tags_all=("topic:finanzas",), tags_any=("tipo:cobranza",)))
    assert [d.key for d in docs] == ["Note:sobre-pago"]


def test_project_no_elegibles_quedan_fuera(tmp_path: Path) -> None:
    """Documentos bajo eligibility.blocked_tags no se seleccionan (lifecycle antes de elegir)."""
    spec = _default_spec()
    spec.manifest["eligibility"] = {"blocked_tags": ["topic:secret"]}
    spec.docs += [
        Doc(
            "Note", "notes/secreto.md", {"id": "secreto", "title": "S", "tags": ["topic:secret"], "body": "x"}
        ),
        Doc(
            "Note",
            "notes/visible.md",
            {"id": "visible", "title": "V", "tags": ["topic:finanzas"], "body": "y"},
        ),
    ]
    root = build(spec, tmp_path / "kb")
    decl = _decl(root)
    keys = {d.key for d in decl.project()}
    assert "Note:visible" in keys
    assert "Note:secreto" not in keys


def test_editorial_tags_never_grant_knowledge_ancestry(build_kb: Callable[[KbSpec], Path]) -> None:
    declarations = _decl(build_kb(_default_spec()))
    assert declarations.project(_selector(models=("KnowledgeDoc",))) == ()


def test_incompatible_registry_ancestor_rejected(build_kb: Callable[[KbSpec], Path]) -> None:
    import pytest

    declarations = _decl(build_kb(_default_spec()))
    kb = declarations._kb  # pyright: ignore[reportPrivateUsage]
    kb.models = [
        model.model_copy(update={"base_models": ["KnowledgeDoc"]}) if model.name == "Note" else model
        for model in kb.models
    ]
    with pytest.raises(ValueError, match="ancestry disagrees"):
        declarations.project(_selector(models=("KnowledgeDoc",)))
