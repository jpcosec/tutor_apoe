"""V13: la norma de identificadores de 13 §4.0 en las relaciones (los nombres los revisa el cargador)."""

from __future__ import annotations

from kb.model.document import Document
from kb.validation.context import ValidationContext
from kb.validation.report import ValidationError
from ontology import DOC_KEY_RE

RELATION_MODEL = "RelationDoc"
_ENDPOINTS = ("source_id", "target_id")


def check_v13(context: ValidationContext) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for relation in (d for d in context.kb.documents if d.is_a(RELATION_MODEL)):
        endpoints = [str(relation.payload.get(field) or "") for field in _ENDPOINTS]
        bad = [e for e in endpoints if not DOC_KEY_RE.match(e)]
        errors += [
            context.error("V13", relation, f"endpoint fuera de la norma Modelo:nombre: {e!r}") for e in bad
        ]
        if not bad and relation.name != expected_name(relation, endpoints):
            errors.append(
                context.error("V13", relation, f"se espera el nombre {expected_name(relation, endpoints)}")
            )
    return errors


def expected_name(relation: Document, endpoints: list[str]) -> str:
    """`<tipo>--<nombre origen>--<nombre destino>` (13 §4.0)."""
    source, target = (endpoint.partition(":")[2] for endpoint in endpoints)
    return f"{relation.payload.get('relation_type')}--{source}--{target}"
