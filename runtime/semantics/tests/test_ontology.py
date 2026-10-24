"""Ontología del runtime (15): vistas, entidades desde la KB, huella, resolve y arranque."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from kb import KnowledgeBase
from kb.views import table_view
from ontology import Ref
from semantics import Ontology, TurnSummaryLike, UnknownRef
from tools import OperationConfigError


def document(key: str, tags: list[str], payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(key=key, model_tags=tags, payload=payload)


class FakeKb:
    """Una KB con una entidad y una tool de operación, sin sldb."""

    fingerprint = "kb-1"

    def __init__(self, entity: str = "pedido") -> None:
        self.documents = [
            document(
                "EntityDoc:entity-pedido",
                ["type.knowledge.entity"],
                {
                    "name": "pedido",
                    "key": "numero",
                    "fields": [
                        {"name": "total", "type": "string", "description": "Total como texto."},
                        {"name": "estado", "type": "string", "personal": True},
                    ],
                },
            ),
            document(
                "ReadToolAtom:tool-pedidos",
                ["type.knowledge.tool", "tool_kind.read"],
                {
                    "name": "mis_pedidos",
                    "description": "d",
                    "entity": entity,
                    "inputs": ["numero"],
                    "bind": ["subject=context.subject"],
                },
            ),
        ]

    def eligible(self) -> list[SimpleNamespace]:
        return self.documents

    def get(self, key: str) -> SimpleNamespace:
        return next(d for d in self.documents if d.key == key)

    def render(self, key: str) -> str:
        return f"texto de {key}"


def fake(entity: str = "pedido") -> Ontology:
    return Ontology(cast(KnowledgeBase, FakeKb(entity)))


@pytest.mark.spec("15-O3")
def test_cambiar_la_plantilla_de_una_vista_cambia_la_huella(monkeypatch: pytest.MonkeyPatch) -> None:
    kb = cast(KnowledgeBase, FakeKb())
    before = Ontology(kb).fingerprint

    changed = table_view("ProfileView", {"dato": "Otro texto.", "valor": "Su valor."})
    monkeypatch.setattr("semantics.ontology.STATIC_VIEWS", (changed,))

    assert Ontology(kb).fingerprint != before
    assert Ontology(kb).fingerprint == Ontology(kb).fingerprint


@pytest.mark.spec("15-O5")
def test_una_tool_sobre_una_entidad_no_declarada_no_arranca() -> None:
    assert [type(t).name for t in Ontology(cast(KnowledgeBase, FakeKb())).operation_tools()] == [
        "mis_pedidos"
    ]
    with pytest.raises(OperationConfigError, match="no declaradas"):
        Ontology(cast(KnowledgeBase, FakeKb(entity="inexistente"))).operation_tools()


@pytest.mark.spec("15-O1")
def test_el_resultado_de_una_tool_se_ve_como_tablas_y_nunca_como_repr() -> None:
    rows = [{"numero": "7", "total": "$9.900"}]

    text = fake().render_tool_result({"tool": "mis_pedidos", "status": "ok", "rows": rows, "count": 1})
    nested = fake().render_tool_result({"tool": "otra", "status": "ok", "envio": {"sid": "SM-1"}})

    assert "| numero | total | estado |" in text
    assert "| 7 | $9.900 |  |" in text
    assert "{'" not in text + nested
    assert '{"sid": "SM-1"}' in nested


@pytest.mark.spec("15-O2")
def test_la_entidad_sale_de_la_kb_y_la_tool_la_usa() -> None:
    ontology = fake()
    pedido = ontology.entity("pedido")
    [tool] = ontology.operation_tools()

    assert (pedido.key, pedido.subject_linked) == ("numero", True)
    assert list(pedido.fields) == ["total", "estado"]
    assert pedido.descriptions["total"] == "Total como texto."
    assert ontology.personal_fields() == {"pedido": frozenset({"estado"})}
    assert set(type(tool).Args.model_fields) == {"numero"}


@pytest.mark.spec("15-O4")
def test_resolve_de_atomo_entidad_y_tool() -> None:
    ontology = fake()

    atom = ontology.resolve(Ref.parse("kb:ReadToolAtom:tool-pedidos"))
    entity = ontology.resolve(Ref(kind="entity", id="pedido"))
    tool = ontology.resolve(Ref(kind="tool", id="mis_pedidos"))

    assert atom.text == "texto de ReadToolAtom:tool-pedidos"
    assert entity.data["key"] == "numero"
    assert tool.text == "mis_pedidos: d"
    with pytest.raises(UnknownRef):
        ontology.resolve(Ref(kind="subject", id="alguien"))
    with pytest.raises(UnknownRef):
        ontology.resolve(Ref(kind="entity", id="inexistente"))


def test_perfil_y_resumen_de_turnos_como_tablas() -> None:
    ontology = Ontology(cast(KnowledgeBase, FakeKb()))
    summary = SimpleNamespace(
        turn=1, question="hola", step_before=None, step_after="step-a", decision="nl", tool=None
    )

    assert "| tipo_empresa | grande |" in ontology.render_profile({"tipo_empresa": "grande", "vacio": None})
    assert ontology.render_profile({}) == ""
    assert "| 1 | hola | — → step-a | nl |  |" in ontology.render_trace([cast(TurnSummaryLike, summary)])


@pytest.mark.spec("15-O6")
def test_el_modulo_no_conoce_nombres_de_negocio() -> None:
    source = Path(__file__).resolve().parents[1] / "src" / "semantics"
    text = "\n".join(p.read_text(encoding="utf-8").lower() for p in source.glob("*.py"))

    assert not [word for word in ("demo", "factura", "folio", "twilio") if word in text]
