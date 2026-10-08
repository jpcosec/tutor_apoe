from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from kb import EmbedderMismatch, IndexNotDeclared, KnowledgeBase
from make_fixture import Doc, KbSpec, minimal

VOCAB = ("pago", "factura", "descuento", "hola")


class BagOfWords:
    """Embedder determinista para pruebas: cuenta palabras de un vocabulario fijo."""

    def id(self) -> str:
        return "fake:bow"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(text.lower().count(word)) + 0.01 for word in VOCAB] for text in texts]


def indexed(build_kb: Callable[[KbSpec], Path]) -> Path:
    spec = minimal()
    spec.manifest["index"] = {"models": ["Note"], "text": "fields:body", "embedder_id": "fake:bow"}
    spec.docs += [
        Doc(
            "Note",
            "notes/sobre-pago.md",
            {"id": "sobre-pago", "title": "p", "tags": [], "body": "pago pago factura"},
        ),
        Doc(
            "Note",
            "notes/sobre-descuento.md",
            {"id": "sobre-descuento", "title": "d", "tags": [], "body": "descuento"},
        ),
    ]
    return build_kb(spec)


def test_rank_con_embedder(build_kb: Callable[[KbSpec], Path]) -> None:
    kb = KnowledgeBase.open(indexed(build_kb), embedder=BagOfWords())

    report = kb.refresh_index()
    hits = kb.rank("quiero hablar del pago", k=2)

    assert report.counts["embedded"] == 4  # tres Note y la SpecialNote (subclase)
    assert hits[0].ref == "Note:sobre-pago"
    assert hits[0].matcher == "fake:bow"
    assert kb.audit_index().clean


def test_rank_restringido_a_among(build_kb: Callable[[KbSpec], Path]) -> None:
    kb = KnowledgeBase.open(indexed(build_kb), embedder=BagOfWords())

    hits = kb.rank("pago", among=["Note:sobre-descuento"])

    assert [h.ref for h in hits] == ["Note:sobre-descuento"]


def test_sin_embedder_cae_a_lexico(build_kb: Callable[[KbSpec], Path]) -> None:
    kb = KnowledgeBase.open(indexed(build_kb))

    assert kb.rank("descuento", k=1)[0].matcher == "difflib"


def test_embedder_distinto_del_declarado(build_kb: Callable[[KbSpec], Path]) -> None:
    class Other(BagOfWords):
        def id(self) -> str:
            return "otro:modelo"

    kb = KnowledgeBase.open(indexed(build_kb), embedder=Other())

    with pytest.raises(EmbedderMismatch):
        kb.rank("pago")


def test_sin_index_declarado(minimal_kb: KnowledgeBase) -> None:
    with pytest.raises(IndexNotDeclared):
        minimal_kb.rank("pago")


def test_proyeccion_all(minimal_kb: KnowledgeBase) -> None:
    projection = minimal_kb.projection()

    assert projection.name == "all"
    assert "Note" in projection.models
    assert projection.relations == ["cites"]
    assert {d.key for d in minimal_kb.in_projection()} == {"Note:nota-a", "SpecialNote:nota-b", "Tool:tool-x"}
    with pytest.raises(KeyError):
        minimal_kb.projection("inexistente")
