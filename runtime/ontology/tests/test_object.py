from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import BaseModel, Field, ValidationError

from ontology import OntologyObject, Provenance, Ref


def r(text: str) -> Ref:
    return Ref.parse(text)


class Nested(BaseModel):
    target: Ref
    extra: list[Ref] = Field(default_factory=list[Ref])


class Sample(OntologyObject):
    schema_version: int = 1
    step: Ref
    nested: Nested
    tags: set[Ref] = Field(default_factory=set[Ref])
    by_name: dict[str, Ref] = Field(default_factory=dict[str, Ref])
    note: object = None


class Inner(OntologyObject):
    schema_version: int = 1
    uses: Ref


class Outer(OntologyObject):
    schema_version: int = 1
    inner: Inner


@pytest.mark.spec("13-I2")
def test_refs_recorre_anidados_en_orden_de_campos() -> None:
    sample = Sample(
        ref=r("turn:s-1:1"),
        step=r("kb:ConversationStep:apertura@a1"),
        nested=Nested(target=r("tool:enviar"), extra=[r("record:factura:1"), r("tool:enviar")]),
        tags={r("subject:9"), r("subject:10")},
        by_name={"z": r("tool:z"), "a": r("tool:a")},
        note=r("tool:no-es-campo-tipado"),
    )

    assert [str(ref) for ref in sample.refs()] == [
        "kb:ConversationStep:apertura@a1",
        "tool:enviar",
        "record:factura:1",
        "subject:10",
        "subject:9",
        "tool:a",
        "tool:z",
        "tool:no-es-campo-tipado",
    ]


@pytest.mark.spec("13-I2")
def test_refs_no_incluye_la_propia_identidad_pero_si_la_de_un_objeto_anidado() -> None:
    outer = Outer(ref=r("turn:s-1:2"), inner=Inner(ref=r("record:factura:7"), uses=r("tool:detalle")))

    assert [str(ref) for ref in outer.refs()] == ["record:factura:7", "tool:detalle"]


def test_procedencia_exige_zona_y_normaliza_a_utc() -> None:
    santiago = timezone(timedelta(hours=-3))

    provenance = Provenance(
        created_by="carga-campana", created_at=datetime(2026, 9, 26, 9, tzinfo=santiago), origin="runtime"
    )

    assert provenance.created_at == datetime(2026, 9, 26, 12, tzinfo=UTC)
    assert provenance.created_at.tzinfo == UTC
    with pytest.raises(ValidationError):
        Provenance(created_by="x", created_at=datetime(2026, 9, 26), origin="authored")
