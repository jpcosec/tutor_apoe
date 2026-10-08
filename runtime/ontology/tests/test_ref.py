import pytest
from pydantic import ValidationError

from ontology import Ref, RefFormatError, RefWithoutRelease

VALID = [
    "kb:ConversationStep:apertura@3b7e",
    "kb:ConversationStep:apertura",
    "kb:DomainAtom:domain-demo-lexico-acciones@rel-2026-09-26_1",
    "tool:registrar_consulta",
    "record:fila_campana:8812",
    "subject:4471",
    "turn:s-9f2c:12",
]


@pytest.mark.spec("13-I5")
@pytest.mark.parametrize("text", VALID)
def test_ida_y_vuelta(text: str) -> None:
    assert str(Ref.parse(text)) == text


@pytest.mark.spec("13-I5")
@pytest.mark.parametrize(
    ("text", "position", "reason"),
    [
        ("kb", 2, "falta ':'"),
        ("KB:DomainAtom:x", 0, "familia desconocida"),
        ("tool:", 5, "vacío"),
        ("kb:DomainAtom:", 14, "vacío"),
        ("kb::x", 3, "vacío"),
        ("tool: registrar", 5, "no permitido"),
        ("tool:registrar ", 14, "no permitido"),
        ("record:fila/campana:1", 11, "no permitido"),
        ("tool:registrar@r1", 14, "solo la familia kb"),
        ("subject:1@r1", 9, "solo la familia kb"),
        ("kb:DomainAtom:x@", 16, "release_id vacío"),
        ("kb:DomainAtom:x@r 1", 17, "no permitido en release_id"),
        ("kb:DomainAtom:x@r.1", 17, "no permitido en release_id"),
        ("kb:DomainAtom:nota.b", 18, "no permitido en identificador"),
        ("kb:domainAtom:x", 3, "no permitido en nombre de modelo"),
        ("tool:Registrar", 5, "no permitido en identificador"),
        ("kb:DomainAtom:x@r@1", 17, "no permitido en release_id"),
        ("kb:DomainAtom", 13, "2 componente"),
        ("tool:a:b", 6, "1 componente"),
        ("turn:s:1:2", 8, "2 componente"),
    ],
)
def test_texto_invalido(text: str, position: int, reason: str) -> None:
    with pytest.raises(RefFormatError) as error:
        Ref.parse(text)

    assert error.value.text == text
    assert error.value.position == position
    assert reason in error.value.reason


@pytest.mark.spec("13-I5")
def test_construccion_directa_respeta_la_gramatica() -> None:
    with pytest.raises(ValidationError):
        Ref(kind="tool", id="x", release_id="r1")
    with pytest.raises(ValidationError):
        Ref(kind="kb", id="solo-un-componente")


def test_parts() -> None:
    assert Ref.parse("turn:s-9f2c:12").parts == ("s-9f2c", "12")


@pytest.mark.spec("13-I3")
def test_require_release() -> None:
    with_release = Ref.parse("kb:ConversationStep:apertura@3b7e")
    tool = Ref.parse("tool:registrar_consulta")

    assert with_release.require_release() is with_release
    assert tool.require_release() is tool
    with pytest.raises(RefWithoutRelease):
        Ref.parse("kb:ConversationStep:apertura").require_release()
