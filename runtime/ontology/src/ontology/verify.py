"""`verify_refs`: comprueba que las referencias de un objeto existen, con un resolutor por familia (§6)."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from pydantic import BaseModel, computed_field

from ontology.base import OntologyObject
from ontology.ref import Ref

Resolver = Callable[[Ref], bool]


class VerifyReport(BaseModel, frozen=True):
    missing: list[Ref]
    unresolved_kinds: list[str]
    checked: int

    @computed_field
    @property
    def ok(self) -> bool:
        return not self.missing


def verify_refs(obj: OntologyObject, resolvers: Mapping[str, Resolver]) -> VerifyReport:
    missing: list[Ref] = []
    unresolved: dict[str, None] = {}
    checked = 0
    for ref in obj.refs():
        resolver = resolvers.get(ref.kind)
        if resolver is None:
            unresolved.setdefault(ref.kind, None)
            continue
        checked += 1
        if not resolver(ref):
            missing.append(ref)
    return VerifyReport(missing=missing, unresolved_kinds=list(unresolved), checked=checked)
