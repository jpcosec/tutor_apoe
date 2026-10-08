"""`KnowledgeBase`: la fachada de solo lectura (spec 01 §7.1)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from kb.exceptions import KnowledgeBaseInvalid
from kb.graph.relations import RelationIndex
from kb.loading import sldb_gateway as sldb
from kb.loading.loader import LoadedKb, load
from kb.model.catalog import KbStats, ModelInfo, Relation, RelationTypeInfo
from kb.model.document import Document
from kb.rendering.materialize import materialize
from kb.retrieval import (
    GOVERNANCE_TAGS,
    Hit,
    IndexAudit,
    IndexReport,
    Projection,
    SemanticIndex,
    projections,
    visible,
)
from kb.tags import check_query_tag, is_under
from kb.validation.report import ValidationReport
from kb.validation.validator import validate

STRUCTURAL = ("RelationDoc", "RelationTypeDoc")


class KnowledgeBase:
    def __init__(self, loaded: LoadedKb, embedder: sldb.Embedder | None = None) -> None:
        self._kb = loaded
        self._scopes: dict[str, frozenset[str]] = {}
        self._embedder = embedder
        self._index: SemanticIndex | None = None
        self._relations = RelationIndex(loaded)
        self.name = loaded.manifest.name
        self.kb_version = loaded.manifest.kb_version
        self.models: list[ModelInfo] = loaded.models

    @classmethod
    def open(cls, root: Path, embedder: sldb.Embedder | None = None) -> KnowledgeBase:
        """Abre y valida; `KnowledgeBaseInvalid` con el reporte completo si hay errores."""
        kb, report = cls.open_lenient(root, embedder)
        if not report.is_valid:
            raise KnowledgeBaseInvalid(report)
        return kb

    @classmethod
    def open_lenient(
        cls, root: Path, embedder: sldb.Embedder | None = None
    ) -> tuple[KnowledgeBase, ValidationReport]:
        """Abre aunque haya errores; solo V0 y C1 bloquean (lanzan como `open`)."""
        loaded, blocking = load(root)
        if loaded is None:
            raise KnowledgeBaseInvalid(ValidationReport.of(blocking))
        kb = cls(loaded, embedder)
        return kb, kb.validate()

    def documents(self) -> list[Document]:
        return list(self._kb.documents)

    def tag_scope(self, tag: str) -> frozenset[str]:
        """El tag y su subárbol en el DAG semántico de sldb, con equivalentes (14 §6.3)."""
        if tag not in self._scopes:
            self._scopes[tag] = sldb.tag_scope(self._kb.store, tag)
        return self._scopes[tag]

    @property
    def fingerprint(self) -> str:
        """La raíz del árbol de Merkle de sldb: misma huella, misma KB (14 §6.1)."""
        return self._kb.fingerprint

    def get(self, ref: str) -> Document:
        """Por `Modelo:nombre` o solo `nombre`; `KeyError` si no existe o si es ambiguo."""
        matches = [d for d in self._kb.documents if ref in (d.key, d.name, str(d.ref))]
        if len(matches) != 1:
            detail = ", ".join(d.key for d in matches) if matches else "ninguno"
            raise KeyError(f"{ref!r} no identifica un documento (candidatos: {detail})")
        return matches[0]

    def by_model(self, model: str, *, include_subclasses: bool = True) -> list[Document]:
        if include_subclasses:
            return [d for d in self._kb.documents if d.is_a(model)]
        return [d for d in self._kb.documents if d.model == model]

    def by_tag(self, tag: str, *, include_descendants: bool = True) -> list[Document]:
        check_query_tag(tag)

        def matches(candidate: str) -> bool:
            return is_under(candidate, tag) if include_descendants else candidate == tag

        return [d for d in self._kb.documents if any(matches(t) for t in d.all_tags)]

    def by_family(self, family: str) -> list[Document]:
        return [d for d in self._kb.documents if (d.family or "") == family]

    def eligible(self) -> list[Document]:
        return [d for d in self._kb.documents if d.eligible]

    def relation_types(self) -> list[RelationTypeInfo]:
        return list(self._relations.types.values())

    def relations(self, relation_type: str) -> list[Relation]:
        return self._relations.of_type(relation_type)

    def outgoing(self, ref: str, relation_type: str | None = None) -> list[Relation]:
        key = self.get(ref).key
        return [r for r in self._authored(relation_type) if r.source_ref == key]

    def incoming(self, ref: str, relation_type: str | None = None) -> list[Relation]:
        key = self.get(ref).key
        return [r for r in self._authored(relation_type) if r.target_ref == key]

    def projection(self, name: str = "all") -> Projection:
        """La `ProjectionDoc` de la KB con ese nombre, o `all` sintetizada (D11); `KeyError` si no existe."""
        return projections(self._kb)[name]

    def governing_models(self) -> list[str]:
        """Los modelos que gobiernan el runtime: `ProjectionDoc` y los de tag de gobierno (spec 16)."""
        governing = {m.name for m in self.models if set(GOVERNANCE_TAGS) & set(m.semantic_tags)}
        return sorted(governing | {"ProjectionDoc"})

    def in_projection(self, name: str = "all") -> list[Document]:
        """Documentos de contenido elegibles que la proyección deja ver."""
        return visible(self._kb.documents, self.projection(name))

    def rank(
        self, query: str, k: int = 10, *, threshold: float = 0.0, among: list[str] | None = None
    ) -> list[Hit]:
        """Los `k` documentos más parecidos a `query` (Corpus de sldb según `kb.index`), entre `among`
        o, por defecto, entre los elegibles de contenido."""
        allowed = among if among is not None else [d.key for d in self.in_projection()]
        return self._semantic().rank(query, k, threshold, allowed)

    def refresh_index(self) -> IndexReport:
        return self._semantic().refresh()

    def audit_index(self) -> IndexAudit:
        return self._semantic().audit()

    def render(self, ref: str) -> str:
        document = self.get(ref)
        return sldb.render(self._kb.model_types[document.model], dict(document.payload))

    def materialize(self) -> str:
        order = self._kb.manifest.materialize.order
        content = [d for d in self._content() if d.eligible]
        return materialize(content, order, lambda d: self.render(d.key))

    def validate(self) -> ValidationReport:
        return validate(self._kb)

    def stats(self) -> KbStats:
        content = self._content()
        by_model = Counter(d.model for d in content)
        return KbStats(
            documents=len(content),
            eligible=sum(d.eligible for d in content),
            by_model={m.name: by_model.get(m.name, 0) for m in self.models if not m.builtin},
            by_family=dict(sorted(Counter(d.family or "" for d in content).items())),
            relations_by_type=self._relations.authored_counts(),
        )

    def _semantic(self) -> SemanticIndex:
        if self._index is None:
            self._index = SemanticIndex(self._kb, self._embedder)
        return self._index

    def _authored(self, relation_type: str | None) -> list[Relation]:
        if relation_type is None:
            return self._relations.authored()
        return self._relations.of_type(relation_type)

    def _content(self) -> list[Document]:
        """Los documentos de contenido: sin relaciones ni modelos propios de sldb (`ProjectionDoc`, …)."""
        return [d for d in self._kb.documents if d.model not in STRUCTURAL and not self._internal(d)]

    def _internal(self, document: Document) -> bool:
        return any(m.builtin for m in self.models if m.name == document.model)
