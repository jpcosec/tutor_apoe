"""Único punto de contacto con sldb (spec 01 §3.0 y §3.6).

Todo sale de `sldb.api`, salvo estas excepciones deliberadas, listadas también en
`tests/test_sldb_boundary.py` (que falla si aparece una nueva):

- `sldb.runtime.validation.Validator`: render de un documento (§3.6, §6.1).
- `sldb.core.exceptions`: el contrato de errores de sldb.
- `sldb.models.builtin_relation_types`: los 11 tipos estructurales (§3.2).

Las huellas del árbol de Merkle salen de `sldb.api.store_fingerprint` (14 §6.1); en el
runtime la raíz se llama `kb_fingerprint` y la de cada documento, `content_hash`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sldb import StructuredNLDoc
from sldb.api import (
    add_model,
    check_edges,
    check_store,
    init_relations,
    init_store,
    load_edge_index,
    load_registered_model,
    load_runtime_documents,
    rebuild_edges,
    track_document_file,
    untrack_document,
    update_store_indexes,
)
from sldb.api import store_fingerprint as sldb_store_fingerprint
from sldb.api.corpus import Corpus, IndexProjection, fields_text, summary_text
from sldb.api.matching import Embedder as Embedder
from sldb.api.semantic import semantic_tag  # pyright: ignore[reportUnknownVariableType]
from sldb.core.exceptions import SLDBError
from sldb.models.builtin_relation_types import BUILTIN_RELATION_TYPES
from sldb.runtime.validation import Validator

BUILTIN_RELATION_NAMES: frozenset[str] = frozenset(str(row["name"]) for row in BUILTIN_RELATION_TYPES)
_NODE_PREFIX = "sldb://document/"


class SldbFailure(Exception):
    """Un error de sldb, envuelto (`raise ... from`)."""


@dataclass(frozen=True)
class LoadedDocument:
    """Lo que el módulo toma de un `RuntimeDocument`."""

    model_name: str
    model_type: type[StructuredNLDoc]
    name: str
    path: str
    payload: dict[str, Any]
    semantic_tags: list[str]


@dataclass(frozen=True)
class StoreFingerprint:
    """El árbol de Merkle de sldb con nombres del runtime.

    `kb_fingerprint` es la raíz (`store_hash`): cambia si cambia cualquier documento o el
    contrato (campos, plantilla) de cualquier modelo.
    `content_hashes` es, por `Modelo:nombre`, el hash de los campos extraídos: lo que se
    renderiza para un agente; cambiar solo el formato del `.md` no lo mueve.
    """

    kb_fingerprint: str
    content_hashes: dict[str, str]


@dataclass(frozen=True)
class StoreDiagnosis:
    """El veredicto de `check_store` en lo que el módulo usa."""

    damaged: list[str]
    mismatched: list[str]
    roster_only: list[str]


def load_documents(store: Path, pythonpath: Path) -> list[LoadedDocument]:
    try:
        documents = load_runtime_documents(store, str(pythonpath))
    except (SLDBError, ImportError) as error:
        raise SldbFailure(f"sldb no pudo cargar los documentos: {error}") from error
    return [
        LoadedDocument(d.model_name, d.model_type, d.name, d.path, dict(d.payload), list(d.semantic_tags))
        for d in documents
    ]


def store_fingerprint(store: Path) -> StoreFingerprint:
    tree = sldb_store_fingerprint(store)
    hashes = {key: document.content_hash for key, document in tree.documents.items()}
    return StoreFingerprint(kb_fingerprint=tree.store_hash, content_hashes=hashes)


def tag_scope(store: Path, tag: str) -> frozenset[str]:
    """El tag, todo lo que está debajo en el DAG semántico y sus equivalentes (sldb `semantic_tag`)."""
    try:
        found = cast(dict[str, Any], semantic_tag(store, tag))
    except (SLDBError, KeyError, ValueError):
        return frozenset({tag})
    related = [
        *cast(list[object], found.get("below") or []),
        *cast(list[object], found.get("equivalents") or []),
    ]
    return frozenset({tag, *(str(t) for t in related)})


def load_model(store: Path, model_name: str, pythonpath: Path) -> type[StructuredNLDoc]:
    try:
        return load_registered_model(store, model_name, str(pythonpath)).model_type
    except (SLDBError, ImportError, AttributeError) as error:
        raise SldbFailure(f"no se pudo importar el modelo {model_name}: {error}") from error


def diagnose(store: Path, root: Path, pythonpath: Path) -> StoreDiagnosis:
    result = check_store(store, root, str(pythonpath))
    return StoreDiagnosis(
        damaged=[f"{d['model']}:{d['doc']}: {d['explain']}" for d in result["damaged"]],
        mismatched=[f"{m['doc']}: {m['kind']} no calza" for m in result["mismatched"]],
        roster_only=[
            f"{model}: el índice cuenta documentos que el árbol no trae" for model in result["roster_only"]
        ],
    )


def stale_documents(store: Path, root: Path, pythonpath: Path) -> list[str]:
    """`Modelo:nombre` de los documentos cuyo texto o campos ya no calzan con el índice."""
    moved = {str(m["doc"]) for m in check_store(store, root, str(pythonpath))["mismatched"]}
    keys = sldb_store_fingerprint(store).documents
    return sorted(key for key in keys if key.partition(":")[2] in moved)


def retrack_document(store: Path, pythonpath: Path, model: str, name: str, path: str, actor: str) -> None:
    """Vuelve a extraer un documento con su mismo modelo y ruta; no toca el `.md`."""
    try:
        untrack_document(store, name, pythonpath=str(pythonpath), actor=actor)
        track_document_file(store, model, path, name=name, pythonpath=str(pythonpath), actor=actor)
    except (SLDBError, ImportError, ValueError) as error:
        raise SldbFailure(f"no se pudo re-extraer {model}:{name}: {error}") from error


def refresh_store_indexes(store: Path, pythonpath: Path) -> None:
    update_store_indexes(store, pythonpath=str(pythonpath), wait=True)


def edge_findings(store: Path) -> list[str]:
    report = check_edges(store, include_linked=False)
    return [*report.errors, *(f"arista desactualizada: {doc}" for doc in report.stale)]


def structural_edges(store: Path, relation_type: str) -> list[tuple[str, str]]:
    index = load_edge_index(store, include_linked=False)
    return [(_bare(e.source), _bare(e.target)) for e in index.edges if e.relation == relation_type]


def render(model_type: type[StructuredNLDoc], payload: dict[str, Any]) -> str:
    return Validator(model_type).render(payload)


def _bare(node_id: str) -> str:
    return node_id.removeprefix(_NODE_PREFIX)


@dataclass(frozen=True)
class RankedDocument:
    """Un documento del corpus con su puntaje, en lo que el módulo usa del `Hit` de sldb."""

    key: str
    score: float


@dataclass(frozen=True)
class CorpusPolicy:
    """La política `kb.index` ya resuelta a modelos concretos (con subclases) y lectura de texto."""

    models: frozenset[str]
    text: str
    text_id: str


def corpus(
    store: Path, pythonpath: Path, derived: Path, policy: CorpusPolicy, embedder: Embedder | None
) -> Corpus:
    """El `Corpus` de sldb para esta KB; sin embedder, sldb cae a difflib (léxico)."""
    return Corpus(store, str(pythonpath), derived, _projection(policy), embedder=embedder)


def rank(corpus: Corpus, query: str, k: int, threshold: float, among: list[str]) -> list[RankedDocument]:
    hits = corpus.rank(query, k=k, threshold=threshold, among=among)
    return [RankedDocument(key=hit.id, score=float(hit.score)) for hit in hits]


def refresh(corpus: Corpus) -> dict[str, int]:
    return dict(corpus.refresh())


def audit(corpus: Corpus) -> dict[str, Any]:
    return dict(corpus.audit())


def matcher_id(corpus: Corpus) -> str:
    return corpus.matcher.id()


def _projection(policy: CorpusPolicy) -> IndexProjection:
    if policy.text.startswith("fields:"):
        names = [name.strip() for name in policy.text.removeprefix("fields:").split(",") if name.strip()]
        reader = fields_text(*names)
    else:
        reader = summary_text
    return IndexProjection.of(models=policy.models, text=reader, text_id=policy.text_id)


#: Modelos que `init_relations` ya registra y documentos que ya escribe: no se repiten al armar.
_SLDB_MODEL_PREFIX = "sldb."
_RELATION_TYPE_MODEL = "RelationTypeDoc"


def registered_models(store: Path, pythonpath: Path, any_model: str) -> list[str]:
    """Las refs (`paquete:Clase`) de los modelos registrados en el store, en su orden."""
    try:
        registered = load_registered_model(store, any_model, str(pythonpath))
    except (SLDBError, ImportError) as error:
        raise SldbFailure(f"sldb no pudo leer los modelos: {error}") from error
    return [str(entry.model_ref) for entry in registered.store_index.models]


def is_structural(model_name: str, payload: dict[str, Any]) -> bool:
    """Un tipo de relación estructural de sldb: `init_relations` lo vuelve a escribir."""
    return model_name == _RELATION_TYPE_MODEL and payload.get("name") in BUILTIN_RELATION_NAMES


def build_store(
    root: Path, pythonpath: Path, model_refs: list[str], documents: list[tuple[str, str, str]], actor: str
) -> None:
    """Un store nuevo en `root/.sldb`: modelos, documentos (`modelo`, `nombre`, `ruta`), índices y aristas.

    Es lo que hace `kb_models rebuild`, pero con la lista de documentos dada en vez de la del
    store anterior (que puede no existir).
    """
    path = str(pythonpath)
    try:
        store = init_store(root, force=True).store_path
        init_relations(store, path)
        for ref in model_refs:
            if not ref.startswith(_SLDB_MODEL_PREFIX):
                add_model(store, ref, pythonpath=path, actor=actor)
        for model, name, relative in documents:
            track_document_file(store, model, root / relative, name=name, pythonpath=path, actor=actor)
        update_store_indexes(store, pythonpath=path, wait=True)
        rebuild_edges(store, path, wait=True)
    except (SLDBError, ImportError) as error:
        raise SldbFailure(f"sldb no pudo armar el store: {error}") from error
