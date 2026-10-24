import pytest
from pydantic import TypeAdapter, ValidationError

from ontology import DocKey, EditorialTag, Identifier, ModelName, SemanticTag

CASES = [
    (Identifier, ["step-demo-respuesta", "registrar_status", "4471"], ["Paso", "a:b", "a.b", "", "-a"]),
    (ModelName, ["ConversationStep", "ToolAtom2"], ["conversationStep", "Tool_Atom", "Tool:Atom"]),
    (DocKey, ["ToolAtom:tool-demo-enviar-template"], ["tool:x", "ToolAtom:a:b", "ToolAtom:a.b"]),
    (SemanticTag, ["type.knowledge.tool", "layer"], ["type:knowledge", "type..tool", "Type.x"]),
    (
        EditorialTag,
        ["domain", "conversation:steps.demo_pagada", "animal:perro.pastor_aleman.firulais"],
        ["ns:", "ns:a:b", "ns:a..b", "Ns:a", "type.knowledge"],
    ),
]


@pytest.mark.spec("13-I6")
@pytest.mark.parametrize(("kind", "valid", "invalid"), CASES)
def test_cada_tipo_acepta_exactamente_su_forma(kind: object, valid: list[str], invalid: list[str]) -> None:
    adapter: TypeAdapter[str] = TypeAdapter(kind)  # pyright: ignore[reportArgumentType]
    for value in valid:
        assert adapter.validate_python(value) == value
    for value in invalid:
        with pytest.raises(ValidationError):
            adapter.validate_python(value)
