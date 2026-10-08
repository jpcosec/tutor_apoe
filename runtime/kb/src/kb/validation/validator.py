"""`validate()`: todas las reglas, sin detenerse en la primera (spec 01 §5)."""

from __future__ import annotations

from collections.abc import Callable

from kb.loading.loader import LoadedKb
from kb.validation.context import ValidationContext
from kb.validation.report import ValidationError, ValidationReport
from kb.validation.rules.data_refs import check_v10
from kb.validation.rules.edges import check_v6, check_v8
from kb.validation.rules.identity import check_v2, check_v3
from kb.validation.rules.kb_documents import check_v7, check_v9
from kb.validation.rules.norm import check_v13
from kb.validation.rules.segments import check_v11, check_v12
from kb.validation.rules.store import check_v1
from kb.validation.rules.tags import check_v4, check_v5

Rule = Callable[[ValidationContext], list[ValidationError]]
RULES: tuple[Rule, ...] = (
    check_v1,
    check_v2,
    check_v3,
    check_v4,
    check_v5,
    check_v6,
    check_v7,
    check_v8,
    check_v9,
    check_v10,
    check_v11,
    check_v12,
    check_v13,
)


def validate(kb: LoadedKb) -> ValidationReport:
    context = ValidationContext(kb)
    return ValidationReport.of([error for rule in RULES for error in rule(context)])
