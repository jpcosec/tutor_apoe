"""El reporte único de validación (spec 01 §5)."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, computed_field

_RULE_NUMBER = re.compile(r"\d+")


class ValidationError(BaseModel, frozen=True):
    """Un hallazgo: qué regla, de dónde viene, sobre qué documento y por qué."""

    rule: str = Field(description="Regla V0..V12.")
    origin: Literal["sldb", "kb"] = Field(description="sldb si lo detectó sldb; kb si el módulo.")
    doc: str | None = Field(default=None, description="'Modelo:nombre' del documento, o None.")
    path: str = Field(default="", description="Ruta relativa a la raíz de la KB.")
    message: str = Field(description="Qué está mal, en una línea.")

    def line(self) -> str:
        """La línea del CLI: cinco columnas separadas por dos espacios (§7.3)."""
        return "  ".join([self.rule, self.origin, self.doc or "-", self.path or "-", self.message])

    def sort_key(self) -> tuple[int, str, str]:
        match = _RULE_NUMBER.search(self.rule)
        return (int(match.group()) if match else -1, self.path, self.message)


class ValidationReport(BaseModel, frozen=True):
    """Todos los hallazgos, ordenados por número de regla y luego por ruta."""

    errors: list[ValidationError] = Field(default_factory=list[ValidationError], description="Hallazgos.")

    @computed_field
    @property
    def is_valid(self) -> bool:
        return not self.errors

    @classmethod
    def of(cls, errors: list[ValidationError]) -> ValidationReport:
        return cls(errors=sorted(errors, key=ValidationError.sort_key))

    def rules(self) -> set[str]:
        return {error.rule for error in self.errors}
