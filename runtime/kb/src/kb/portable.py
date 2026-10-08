"""Una KB como archivos fuente más su índice (spec 17): exportarla y rearmar su store en otro lado.

El store (`.sldb/`) es derivado, pero para rearmarlo hay que saber con qué modelo se trackeó cada
archivo; eso es lo que guarda `StoreSources` junto a los archivos.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from kb.declaration.manifest import load_manifest
from kb.exceptions import KnowledgeBaseInvalid
from kb.loading import sldb_gateway as sldb
from kb.loading.loader import STORE_DIR
from kb.validation.report import ValidationReport

ACTOR = "antonia bundle"
#: El historial de sesiones de pron no es conocimiento del negocio (igual que `kb_models rebuild`).
SESSION_MODELS = frozenset({"MoveDoc", "AnchorDoc"})


class TrackedSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model: str = Field(description="Modelo con el que se trackea.")
    name: str = Field(description="Nombre del documento en el store.")
    path: str = Field(description="Ruta del `.md`, relativa a la raíz de la KB.")


class StoreSources(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    models: list[str] = Field(description="Refs de los modelos registrados (`paquete:Clase`), en orden.")
    documents: list[TrackedSource] = Field(description="Cada documento con su modelo, ordenados por ruta.")


def store_sources(root: Path) -> StoreSources:
    """Qué modelos registra el store de la KB y con qué modelo está cada documento."""
    root = root.resolve()
    store, pythonpath = root / STORE_DIR, _pythonpath(root)
    loaded = [
        d
        for d in sldb.load_documents(store, pythonpath)
        if d.model_name not in SESSION_MODELS and not sldb.is_structural(d.model_name, d.payload)
    ]
    documents = sorted(
        (TrackedSource(model=d.model_name, name=d.name, path=d.path) for d in loaded), key=lambda s: s.path
    )
    models = sldb.registered_models(store, pythonpath, loaded[0].model_name) if loaded else []
    return StoreSources(models=models, documents=documents)


def build_store(root: Path, sources: StoreSources) -> None:
    """Rearma `root/.sldb` desde los `.md` que ya están en `root` y el índice de `sources`."""
    root = root.resolve()
    documents = [(d.model, d.name, d.path) for d in sources.documents]
    sldb.build_store(root, _pythonpath(root), sources.models, documents, ACTOR)


def _pythonpath(root: Path) -> Path:
    manifest, errors = load_manifest(root)
    if manifest is None:
        raise KnowledgeBaseInvalid(ValidationReport(errors=errors))
    return manifest.resolved_pythonpath(root)
