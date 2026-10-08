"""V4 (sintaxis de tags editoriales) y V5 (categorías)."""

from __future__ import annotations

from kb.model.document import Document
from kb.tags import is_editorial, namespace
from kb.validation.context import ValidationContext
from kb.validation.report import ValidationError

CATEGORY = "type.kb.category"


def check_v4(context: ValidationContext) -> list[ValidationError]:
    return [
        context.error("V4", document, f"tag editorial inválido: {tag!r}")
        for document in context.kb.documents
        for tag in document.tags
        if not is_editorial(tag)
    ]


def check_v5(context: ValidationContext) -> list[ValidationError]:
    categories = context.with_model_tag(CATEGORY)
    errors = [
        context.error("V5", c, "una categoría necesita tag: str y parent")
        for c in categories
        if not _shaped(c)
    ]
    if context.kb.manifest.categories != "required":
        return errors
    declared = {str(c.payload["tag"]) for c in categories if _shaped(c)}
    return [*errors, *_orphan_parents(context, categories, declared), *_uncategorized(context, declared)]


def _shaped(category: Document) -> bool:
    # sldb omite del payload un campo optrev vacío: un parent ausente es None (01 §4.3, N3).
    parent = category.payload.get("parent")
    return isinstance(category.payload.get("tag"), str) and (parent is None or isinstance(parent, str))


def _orphan_parents(
    context: ValidationContext, categories: list[Document], declared: set[str]
) -> list[ValidationError]:
    return [
        context.error("V5", c, f"parent {c.payload.get('parent')!r} no es el tag de otra categoría")
        for c in categories
        if _shaped(c) and c.payload.get("parent") is not None and c.payload.get("parent") not in declared
    ]


def _uncategorized(context: ValidationContext, declared: set[str]) -> list[ValidationError]:
    return [
        context.error("V5", document, f"tag sin categoría: {tag!r}")
        for document in context.kb.documents
        for tag in document.tags
        if tag not in declared and namespace(tag) not in declared
    ]
