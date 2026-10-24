"""`OntologyObject`: la raíz de la que derivan documentos, tools, registros y trazas (spec 13 §7)."""

from __future__ import annotations

from collections.abc import Iterator

from pydantic import BaseModel

from ontology.provenance import Provenance
from ontology.ref import Ref


class OntologyObject(BaseModel):
    ref: Ref
    schema_version: int
    provenance: Provenance | None = None

    def refs(self) -> list[Ref]:
        """Todas las referencias del objeto, sin `self.ref`, en orden de campos y sin duplicados (§6)."""
        seen: dict[Ref, None] = {}
        for name in type(self).model_fields:
            if name == "ref":
                continue
            for found in _walk(getattr(self, name)):
                seen.setdefault(found, None)
        return list(seen)


def _walk(value: object) -> Iterator[Ref]:
    if isinstance(value, Ref):
        yield value
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from _walk(getattr(value, name))
    elif isinstance(value, list | tuple):
        for element in value:  # pyright: ignore[reportUnknownVariableType]
            yield from _walk(element)  # pyright: ignore[reportUnknownArgumentType]
    elif isinstance(value, set | frozenset):
        for element in sorted(value, key=str):  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
            yield from _walk(element)  # pyright: ignore[reportUnknownArgumentType]
    elif isinstance(value, dict):
        for key in sorted(value, key=str):  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
            yield from _walk(value[key])  # pyright: ignore[reportUnknownArgumentType]
