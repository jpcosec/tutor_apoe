"""V1, la parte que no bloquea la apertura: store en PASS, origen de los modelos, `__family__`."""

from __future__ import annotations

import re

from kb.validation.context import ValidationContext
from kb.validation.report import ValidationError

_FAMILY = re.compile(r"^[a-z][a-z0-9_]*$")
_KB_BASE = "kb_base"


def check_v1(context: ValidationContext) -> list[ValidationError]:
    return [*_store_diagnosis(context), *_model_origins(context), *_families(context)]


def _store_diagnosis(context: ValidationContext) -> list[ValidationError]:
    diagnosis = context.kb.diagnosis
    return [
        ValidationError(rule="V1", origin="sldb", message=f"check_store: {finding}")
        for finding in [*diagnosis.damaged, *diagnosis.mismatched, *diagnosis.roster_only]
    ]


def _model_origins(context: ValidationContext) -> list[ValidationError]:
    package = context.kb.manifest.models
    return [
        ValidationError(rule="V1", origin="kb", message=f"{m.name}: {m.model_ref} no es de {package}")
        for m in context.kb.models
        if not m.builtin and not _belongs(m.model_ref, package) and not _belongs(m.model_ref, _KB_BASE)
    ]


def _families(context: ValidationContext) -> list[ValidationError]:
    return [
        ValidationError(rule="V1", origin="kb", message=f"{name}: __family__ {family!r} no cumple el patrón")
        for name, model_type in context.kb.model_types.items()
        if (family := getattr(model_type, "__family__", None)) is not None
        and not (isinstance(family, str) and _FAMILY.match(family))
    ]


def _belongs(model_ref: str, package: str) -> bool:
    module = model_ref.split(":", 1)[0]
    return module == package or module.startswith(package + ".")
