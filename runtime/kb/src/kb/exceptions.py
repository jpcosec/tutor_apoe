"""Errores propios del módulo (spec 01 §7.2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kb.validation.report import ValidationReport


class KnowledgeBaseError(Exception):
    """Raíz de los errores del módulo."""


class KnowledgeBaseNotFound(KnowledgeBaseError):
    """No hay `kb.yaml` en la raíz indicada."""


class KnowledgeBaseInvalid(KnowledgeBaseError):
    """La KB no pasa la validación; `report` trae todos los hallazgos."""

    def __init__(self, report: ValidationReport) -> None:
        lines = "\n".join(error.line() for error in report.errors)
        super().__init__(f"KB inválida ({len(report.errors)} errores):\n{lines}")
        self.report = report


class IndexNotDeclared(KnowledgeBaseError):
    """Se pidió el índice semántico y `kb.yaml` no declara `index`."""


class EmbedderMismatch(KnowledgeBaseError):
    """El embedder recibido no es el que declara `kb.index.embedder_id` (vectores incomparables)."""
