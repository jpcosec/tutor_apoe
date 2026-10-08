"""V11 (`applies_when`) y V12 (roles únicos), spec 01 §6.4."""

from __future__ import annotations

import re

from kb.model.document import Document
from kb.payload import str_list
from kb.validation.context import ValidationContext
from kb.validation.report import ValidationError

_VALUE = r"[A-Za-z0-9_.-]+"
CONDITION = re.compile(
    rf"^(?:profile\.[a-z][a-z0-9_]*(?: (?:==|!=) {_VALUE}| in \[{_VALUE}(?:, {_VALUE})*\])"
    r"|trait:(?P<trait>[a-z][a-z0-9_-]*))$"
)
SEGMENTED_ROLES = {
    "style": ("self.style", "type.knowledge.style"),
    "strategy": ("self.strategy", "type.knowledge.strategy"),
}
REGISTRATION_ENTRY = "type.knowledge.registration_entry"


def check_v11(context: ValidationContext) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for document in context.kb.documents:
        for condition in _conditions(document):
            match = CONDITION.match(condition)
            if match is None:
                errors.append(
                    context.error("V11", document, f"condición fuera de la gramática: {condition!r}")
                )
            elif (trait := match.group("trait")) and trait not in context.trait_ids:
                errors.append(context.error("V11", document, f"trait:{trait} no existe en la KB"))
    return errors


def check_v12(context: ValidationContext) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for role, tags in SEGMENTED_ROLES.items():
        general = [d for d in context.kb.documents if set(tags) & set(d.all_tags) and not _conditions(d)]
        if len(general) > 1:
            names = ", ".join(d.key for d in general)
            errors.append(context.error("V12", general[1], f"dos variantes generales de {role}: {names}"))
    entries = [d for d in context.kb.documents if REGISTRATION_ENTRY in d.all_tags]
    if len(entries) > 1:
        names = ", ".join(d.key for d in entries)
        errors.append(context.error("V12", entries[1], f"más de una entrada de registro: {names}"))
    return errors


def _conditions(document: Document) -> list[str]:
    return str_list(document.payload.get("applies_when"))
