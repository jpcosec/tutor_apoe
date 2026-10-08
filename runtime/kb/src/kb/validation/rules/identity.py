"""V2 (id igual al nombre) y V3 (nombres únicos en toda la KB)."""

from __future__ import annotations

from kb.validation.context import ValidationContext
from kb.validation.report import ValidationError


def check_v2(context: ValidationContext) -> list[ValidationError]:
    return [
        context.error("V2", document, f"id {document.payload['id']!r} distinto del nombre {document.name!r}")
        for document in context.kb.documents
        if "id" in document.payload and document.payload["id"] != document.name
    ]


def check_v3(context: ValidationContext) -> list[ValidationError]:
    return [
        context.error("V3", documents[0], f"nombre repetido en {', '.join(d.key for d in documents)}")
        for documents in context.by_name.values()
        if len(documents) > 1
    ]
