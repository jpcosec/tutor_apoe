"""V10: la KB no apunta a los datos; ningún documento contiene una `Ref` record/subject/turn (13 I4)."""

from __future__ import annotations

from pydantic import ValidationError as PydanticValidationError

from kb.payload import walk_strings
from kb.validation.context import ValidationContext
from kb.validation.report import ValidationError
from ontology import Ref, RefFormatError

DATA_KINDS = ("record", "subject", "turn")


def check_v10(context: ValidationContext) -> list[ValidationError]:
    return [
        context.error("V10", document, f"la KB apunta a datos: {text}")
        for document in context.kb.documents
        for text in walk_strings(document.payload)
        if _is_data_ref(text)
    ]


def _is_data_ref(text: str) -> bool:
    if not text.startswith(tuple(f"{kind}:" for kind in DATA_KINDS)):
        return False
    try:
        Ref.parse(text)
    except (RefFormatError, PydanticValidationError):
        return False
    return True
