"""V6 (lo que comprueba `check_edges` de sldb) y V8 (referencias con modelo exacto o ancestro)."""

from __future__ import annotations

from kb.loading import sldb_gateway as sldb
from kb.validation.context import ValidationContext
from kb.validation.report import ValidationError

RELATION_MODEL = "RelationDoc"
_ENDPOINTS = ("source_id", "target_id")


def check_v6(context: ValidationContext) -> list[ValidationError]:
    return [
        ValidationError(rule="V6", origin="sldb", message=finding)
        for finding in sldb.edge_findings(context.kb.store)
    ]


def check_v8(context: ValidationContext) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for relation in (d for d in context.kb.documents if d.is_a(RELATION_MODEL)):
        for field in _ENDPOINTS:
            reference = str(relation.payload.get(field) or "")
            if reference.count(":") > 1:
                errors.append(context.error("V8", relation, f"{field} de store enlazado: {reference}"))
            elif context.by_name.get(reference.partition(":")[2]) and not context.resolves(reference):
                errors.append(
                    context.error("V8", relation, f"{field} {reference} no es del modelo ni ancestro")
                )
    return errors
