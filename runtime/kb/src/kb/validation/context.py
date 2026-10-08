"""Lo que las reglas de validación necesitan leer de una KB cargada, indexado una vez."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property

from kb.loading.loader import LoadedKb
from kb.model.document import Document
from kb.validation.report import ValidationError


@dataclass
class ValidationContext:
    kb: LoadedKb
    by_key: dict[str, Document] = field(init=False)
    by_name: dict[str, list[Document]] = field(init=False)

    def __post_init__(self) -> None:
        self.by_key = {document.key: document for document in self.kb.documents}
        grouped: dict[str, list[Document]] = defaultdict(list)
        for document in self.kb.documents:
            grouped[document.name].append(document)
        self.by_name = dict(grouped)

    def with_model_tag(self, tag: str) -> list[Document]:
        return [document for document in self.kb.documents if tag in document.model_tags]

    @cached_property
    def trait_ids(self) -> set[str]:
        return {document.name for document in self.with_model_tag("type.knowledge.trait")}

    def resolves(self, reference: str) -> bool:
        """`Modelo:nombre` existe con ese modelo exacto o con un modelo que desciende de él (V7, V8)."""
        model, _, name = reference.partition(":")
        return any(document.is_a(model) for document in self.by_name.get(name, []))

    def error(self, rule: str, document: Document | None, message: str) -> ValidationError:
        return ValidationError(
            rule=rule,
            origin="kb",
            doc=document.key if document else None,
            path=document.path if document else "",
            message=message,
        )
