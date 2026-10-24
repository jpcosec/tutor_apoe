"""Abrir una KB: manifiesto, store, modelos y documentos, con los errores que bloquean (spec 01 §7.1)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sldb import StructuredNLDoc

from kb.declaration.manifest import KbManifest, load_manifest
from kb.loading import sldb_gateway as sldb
from kb.loading.documents import build_document
from kb.loading.store_index import registered_models
from kb.model.catalog import ModelInfo
from kb.model.document import Document
from kb.validation.report import ValidationError
from ontology import IDENTIFIER_RE

STORE_DIR = ".sldb"


@dataclass(frozen=True)
class LoadedKb:
    root: Path
    manifest: KbManifest
    store: Path
    pythonpath: Path
    models: list[ModelInfo]
    model_types: dict[str, type[StructuredNLDoc]]
    documents: list[Document]
    diagnosis: sldb.StoreDiagnosis
    fingerprint: str = ""


def load(root: Path) -> tuple[LoadedKb | None, list[ValidationError]]:
    """La KB cargada, o `None` con los errores que bloquean: V0, la parte de V1 de C1 y V13."""
    root = root.resolve()
    manifest, errors = load_manifest(root)
    if manifest is None:
        return None, errors
    store, pythonpath = root / STORE_DIR, manifest.resolved_pythonpath(root)
    if not store.is_dir():
        return None, [_v1(f"no hay store {STORE_DIR}/ en la KB")]
    models = registered_models(store)
    model_types, errors = _import_models(store, models, pythonpath)
    if errors:
        return None, errors
    diagnosis = sldb.diagnose(store, root, pythonpath)
    loaded = sldb.load_documents(store, pythonpath)
    errors = [*_check_counts(models, loaded), *_check_names(loaded)]
    if errors:
        return None, errors
    fingerprint = sldb.store_fingerprint(store)
    documents = _documents(loaded, models, root, manifest, fingerprint.content_hashes)
    kb = LoadedKb(
        root,
        manifest,
        store,
        pythonpath,
        models,
        model_types,
        documents,
        diagnosis,
        fingerprint.kb_fingerprint,
    )
    return kb, []


def _import_models(
    store: Path, models: list[ModelInfo], pythonpath: Path
) -> tuple[dict[str, type[StructuredNLDoc]], list[ValidationError]]:
    types: dict[str, type[StructuredNLDoc]] = {}
    errors: list[ValidationError] = []
    for model in models:
        try:
            types[model.name] = sldb.load_model(store, model.name, pythonpath)
        except sldb.SldbFailure as failure:
            errors.append(_v1(str(failure), origin="sldb"))
    return types, errors


def _check_counts(models: list[ModelInfo], loaded: list[sldb.LoadedDocument]) -> list[ValidationError]:
    """C1: sldb omite en silencio los modelos que no importa; el conteo lo delata."""
    counts = Counter(document.model_name for document in loaded)
    return [
        _v1(f"{m.name}: el índice registra {m.documents_count} documentos y se cargaron {counts[m.name]}")
        for m in models
        if m.documents_count > 0 and counts[m.name] != m.documents_count
    ]


def _check_names(loaded: list[sldb.LoadedDocument]) -> list[ValidationError]:
    """V13: sin un nombre según 13 §4.0 no hay identidad (`Ref`) que construir; bloquea."""
    return [
        ValidationError(
            rule="V13",
            origin="kb",
            doc=f"{d.model_name}:{d.name}",
            path=d.path,
            message=f"nombre fuera de la norma de identificadores: {d.name!r}",
        )
        for d in loaded
        if not IDENTIFIER_RE.match(d.name)
    ]


def _documents(
    loaded: list[sldb.LoadedDocument],
    models: list[ModelInfo],
    root: Path,
    manifest: KbManifest,
    content_hashes: dict[str, str],
) -> list[Document]:
    refs = {model.name: model.model_ref for model in models}
    blocked = manifest.eligibility.blocked_tags
    documents = [
        build_document(
            d, refs.get(d.model_name, ""), root, blocked, content_hashes.get(f"{d.model_name}:{d.name}", "")
        )
        for d in loaded
    ]
    return sorted(documents, key=lambda document: document.key)


def _v1(message: str, origin: str = "kb") -> ValidationError:
    return ValidationError(rule="V1", origin=origin, message=message)  # pyright: ignore[reportArgumentType]
