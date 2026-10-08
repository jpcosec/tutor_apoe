"""Proyecciones y recuperación por similitud (spec 01 §6.3, D11; decisión de embeddings E1–E5).

Nada se implementa aquí: el índice, el refresco, la auditoría y el ranking son el
`Corpus` de sldb; este módulo solo resuelve la política `kb.index` a modelos concretos,
restringe el ranking a lo elegible (o a una proyección) y devuelve documentos.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from kb.exceptions import EmbedderMismatch, IndexNotDeclared
from kb.loading import sldb_gateway as sldb
from kb.loading.loader import LoadedKb
from kb.model.document import Document
from kb.payload import as_list, as_mapping, str_list

INDEX_DIR = Path(".sldb") / "runtime" / "cache" / "corpus"
PROJECTION_TAG = "type.knowledge.projection"
#: Los documentos que gobiernan el runtime (spec 16): los cambian personas y ningún agente los ve.
GOVERNANCE_TAGS = ("type.governance.agent", "type.governance.pipeline")
NOT_CONTENT_TAGS = ("type.kb.category", "type.kb.reference", "type.kb.tool_test", *GOVERNANCE_TAGS)


class Projection(BaseModel, frozen=True):
    """Qué modelos y relaciones ve un consumidor (el `ProjectionDoc` de pron, en lo que el runtime lee)."""

    name: str = Field(description="Nombre de la proyección; `all` si la KB no declara ninguna.")
    models: list[str] = Field(description="Modelos visibles; sus subclases también.")
    relations: list[str] = Field(description="Tipos de relación visibles.")


class Hit(BaseModel, frozen=True):
    ref: str = Field(description="Modelo:nombre.")
    model: str = Field(description="Clase del documento.")
    name: str = Field(description="Nombre del documento.")
    score: float = Field(description="Similitud según el matcher.")
    matcher: str = Field(description="Id del embedder usado, o 'difflib' en modo léxico.")
    document: Document = Field(description="El documento.")


class IndexReport(BaseModel, frozen=True):
    counts: dict[str, int] = Field(description="Lo que sldb embebió, reutilizó y descartó.")
    index_path: str = Field(description="Dónde quedó el índice (derivado, fuera de git).")


class IndexAudit(BaseModel, frozen=True):
    missing: list[str] = Field(description="Documentos sin vector.")
    stale: list[str] = Field(description="Documentos cuyo texto cambió.")
    orphan: list[str] = Field(description="Vectores de documentos que ya no están.")
    clean: bool = Field(description="Sin nada de lo anterior.")


class SemanticIndex:
    """El corpus de una KB, con un embedder inyectado o, sin él, en modo léxico (difflib de sldb)."""

    def __init__(self, kb: LoadedKb, embedder: sldb.Embedder | None) -> None:
        policy = kb.manifest.index
        if policy is None:
            raise IndexNotDeclared(f"{kb.manifest.name}: kb.yaml no declara index")
        if embedder is not None and embedder.id() != policy.embedder_id:
            raise EmbedderMismatch(f"la KB se indexa con {policy.embedder_id}; se recibió {embedder.id()}")
        models = _with_subclasses(kb, policy.models)
        resolved = sldb.CorpusPolicy(models=frozenset(models), text=policy.text, text_id=policy.text_id)
        self._corpus = sldb.corpus(kb.store, kb.pythonpath, kb.root / INDEX_DIR, resolved, embedder)
        self._documents = {d.key: d for d in kb.documents}

    @property
    def matcher(self) -> str:
        return sldb.matcher_id(self._corpus)

    def rank(self, query: str, k: int, threshold: float, among: list[str]) -> list[Hit]:
        ranked = sldb.rank(self._corpus, query, k, threshold, among)
        return [self._hit(r) for r in ranked if r.key in self._documents]

    def refresh(self) -> IndexReport:
        counts = sldb.refresh(self._corpus)
        return IndexReport(counts=counts, index_path=str(self._corpus.index_path))

    def audit(self) -> IndexAudit:
        found = sldb.audit(self._corpus)
        missing, stale, orphan = (str_list(found.get(key)) for key in ("missing", "stale", "orphan"))
        return IndexAudit(missing=missing, stale=stale, orphan=orphan, clean=not (missing or stale or orphan))

    def _hit(self, ranked: sldb.RankedDocument) -> Hit:
        document = self._documents[ranked.key]
        return Hit(
            ref=document.key,
            model=document.model,
            name=document.name,
            score=ranked.score,
            matcher=self.matcher,
            document=document,
        )


def projections(kb: LoadedKb) -> dict[str, Projection]:
    """Las `ProjectionDoc` de la KB, más `all` sintetizada si la KB no declara una con ese nombre."""
    declared = {p.name: p for p in (_projection(d) for d in kb.documents if PROJECTION_TAG in d.model_tags)}
    declared.setdefault("all", _all(kb))
    return declared


def visible(documents: list[Document], projection: Projection) -> list[Document]:
    """Documentos de contenido elegibles cuyo modelo (o ancestro) está en la proyección."""
    return [
        d
        for d in documents
        if d.eligible
        and not set(NOT_CONTENT_TAGS) & set(d.model_tags)
        and any(d.is_a(model) for model in projection.models)
    ]


def _with_subclasses(kb: LoadedKb, models: list[str]) -> list[str]:
    """`kb.index.models` nombra jerarquías (`{Modelo+}`); vacío es todo modelo de contenido."""
    content = [m for m in kb.models if not m.builtin]
    if not models:
        return [m.name for m in content]
    return [m.name for m in content if m.name in models or set(models) & set(m.base_models)]


def _projection(document: Document) -> Projection:
    relations = [
        str((as_mapping(r) or {}).get("name", "")) for r in as_list(document.payload.get("relations")) or []
    ]
    return Projection(
        name=str(document.payload.get("name") or document.name),
        models=str_list(document.payload.get("models")),
        relations=[r for r in relations if r],
    )


def _all(kb: LoadedKb) -> Projection:
    """Todo el conocimiento de la KB, sin los modelos que gobiernan el runtime (spec 16)."""
    authored = sorted(
        {
            str(d.payload.get("name"))
            for d in kb.documents
            if d.model == "RelationTypeDoc" and d.payload.get("name")
        }
        - set(sldb.BUILTIN_RELATION_NAMES)
    )
    models = [m.name for m in kb.models if not m.builtin and not set(GOVERNANCE_TAGS) & set(m.semantic_tags)]
    return Projection(name="all", models=models, relations=authored)
