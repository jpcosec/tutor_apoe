"""V7 (conversaciones de referencia) y V9 (pruebas de tool), reconocidas por tag semántico."""

from __future__ import annotations

import json

from kb.model.document import Document
from kb.payload import as_list, as_mapping, walk_strings
from kb.validation.context import ValidationContext
from kb.validation.report import ValidationError
from ontology import DOC_KEY_RE

REFERENCE = "type.kb.reference"
TOOL_TEST = "type.kb.tool_test"
TOOL = "type.knowledge.tool"
TURN_SHAPE = "turns debe ser [{who: user|agent, text, expect}]"
TEST_SHAPE = "una prueba de tool necesita tool: str, args y expect"


def check_v7(context: ValidationContext) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for document in context.with_model_tag(REFERENCE):
        turns = as_list(document.payload.get("turns"))
        if turns is None or not all(_is_turn(turn) for turn in turns):
            errors.append(context.error("V7", document, TURN_SHAPE))
            continue
        cited = (text for text in walk_strings(turns) if DOC_KEY_RE.match(text))
        errors += [
            context.error("V7", document, f"expect cita {ref}, que no existe")
            for ref in cited
            if not context.resolves(ref)
        ]
    return errors


def check_v9(context: ValidationContext) -> list[ValidationError]:
    names = {name for tool in context.with_model_tag(TOOL) if (name := tool_name(tool))}
    errors: list[ValidationError] = []
    for test in context.with_model_tag(TOOL_TEST):
        payload = test.payload
        tool = payload.get("tool")
        if (
            not isinstance(tool, str)
            or as_mapping(payload.get("args")) is None
            or as_mapping(payload.get("expect")) is None
        ):
            errors.append(context.error("V9", test, TEST_SHAPE))
        elif tool not in names:
            errors.append(context.error("V9", test, f"tool {tool!r} no está declarada en la KB"))
    return errors


def tool_name(tool: Document) -> str | None:
    """El `name` de una tool declarada: el del JSON de `parameters`, o un campo `name`."""
    parameters: object = tool.payload.get("parameters")
    if isinstance(parameters, str):
        try:
            parameters = json.loads(parameters)
        except json.JSONDecodeError:
            return None
    source = as_mapping(parameters) or tool.payload
    name = source.get("name")
    return name if isinstance(name, str) else None


def _is_turn(turn: object) -> bool:
    fields = as_mapping(turn)
    if fields is None:
        return False
    expect = fields.get("expect")
    speaks = fields.get("who") in ("user", "agent") and isinstance(fields.get("text"), str)
    return speaks and (expect is None or as_mapping(expect) is not None)
