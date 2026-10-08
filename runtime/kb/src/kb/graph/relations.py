"""Relaciones por tipo con sus endpoints resueltos (spec 01 §7.1); no hay grafo propio (§3.0)."""

from __future__ import annotations

from collections import defaultdict

from kb.loading import sldb_gateway as sldb
from kb.loading.loader import LoadedKb
from kb.model.catalog import Relation, RelationTypeInfo
from kb.model.document import Document
from kb.payload import str_list

RELATION_MODEL = "RelationDoc"
RELATION_TYPE_MODEL = "RelationTypeDoc"


class RelationIndex:
    """Las aristas autoradas salen de los `RelationDoc`; las estructurales, del índice de sldb."""

    def __init__(self, kb: LoadedKb) -> None:
        self._kb = kb
        self.types = {info.name: info for info in _relation_types(kb.documents)}
        self._authored: dict[str, list[Relation]] = defaultdict(list)
        for document in kb.documents:
            if document.is_a(RELATION_MODEL):
                relation = _relation(document)
                self._authored[relation.relation_type].append(relation)

    def of_type(self, relation_type: str) -> list[Relation]:
        if relation_type not in self.types:
            raise KeyError(f"tipo de relación no declarado: {relation_type}")
        if self.types[relation_type].builtin:
            edges = sldb.structural_edges(self._kb.store, relation_type)
            return _sorted(
                [Relation(source_ref=s, target_ref=t, relation_type=relation_type) for s, t in edges]
            )
        return _sorted(self._authored.get(relation_type, []))

    def authored(self) -> list[Relation]:
        return _sorted([relation for relations in self._authored.values() for relation in relations])

    def authored_counts(self) -> dict[str, int]:
        return {
            name: len(self._authored.get(name, [])) for name, info in self.types.items() if not info.builtin
        }


def _relation(document: Document) -> Relation:
    payload = document.payload
    return Relation(
        source_ref=str(payload.get("source_id") or ""),
        target_ref=str(payload.get("target_id") or ""),
        relation_type=str(payload.get("relation_type") or ""),
        condition=str(payload.get("condition") or ""),
        doc=document,
    )


def _relation_types(documents: list[Document]) -> list[RelationTypeInfo]:
    infos = [_relation_type(document) for document in documents if document.is_a(RELATION_TYPE_MODEL)]
    return sorted(infos, key=lambda info: info.name)


def _relation_type(document: Document) -> RelationTypeInfo:
    payload = document.payload
    name = str(payload.get("name") or document.name)
    return RelationTypeInfo(
        name=name,
        direction=str(payload.get("direction") or ""),
        cardinality=str(payload.get("cardinality") or ""),
        axis=str(payload.get("axis") or ""),
        source_types=str_list(payload.get("source_types")),
        target_types=str_list(payload.get("target_types")),
        condition=str(payload.get("condition") or ""),
        description=str(payload.get("description") or ""),
        builtin=name in sldb.BUILTIN_RELATION_NAMES,
    )


def _sorted(relations: list[Relation]) -> list[Relation]:
    return sorted(relations, key=lambda r: (r.source_ref, r.target_ref))
