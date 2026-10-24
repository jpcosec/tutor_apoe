"""Re-extracción (spec 01 §6.3): el store vuelve a ser función de los `.md` con el sldb vigente.

Es la respuesta a un V1 con `origin=sldb` (el derivado quedó atrás del extractor) y el paso
previo al manifiesto en 09. Escribe en el store, nunca en los `.md`; el runtime en servicio
no la llama.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from kb.declaration.manifest import load_manifest
from kb.exceptions import KnowledgeBaseInvalid
from kb.loading import sldb_gateway as sldb
from kb.loading.loader import STORE_DIR
from kb.validation.report import ValidationReport

ACTOR = "antonia retrack"


class RetrackReport(BaseModel, frozen=True):
    retracked: list[str] = Field(default_factory=list[str], description="Re-extraídos: `Modelo:nombre`.")
    unchanged: list[str] = Field(default_factory=list[str], description="Pedidos cuya huella ya calzaba.")
    failed: list[str] = Field(default_factory=list[str], description="`Modelo:nombre: motivo`.")
    would_retrack: list[str] = Field(
        default_factory=list[str],
        description="Con `dry_run`: los que se re-extraerían. El store no se tocó.",
    )


def retrack(root: Path, refs: list[str] | None = None, dry_run: bool = False) -> RetrackReport:
    """Re-extrae los documentos que no calzan (todos, o solo los de `refs`).

    Con `dry_run` no escribe: informa en `would_retrack` qué tocaría. Sirve para medir el alcance
    antes de un cambio de esquema, que deja atrás el derivado de cada documento (§6.3).
    """
    root = root.resolve()
    manifest, errors = load_manifest(root)
    if manifest is None:
        raise KnowledgeBaseInvalid(ValidationReport(errors=errors))
    store, pythonpath = root / STORE_DIR, manifest.resolved_pythonpath(root)
    stale = sldb.stale_documents(store, root, pythonpath)
    wanted = stale if refs is None else [ref for ref in stale if ref in refs]
    if dry_run:
        return RetrackReport(would_retrack=wanted, unchanged=sorted(set(refs or []) - set(stale)))
    paths = {f"{d.model_name}:{d.name}": d.path for d in sldb.load_documents(store, pythonpath)}
    retracked: list[str] = []
    failed: list[str] = []
    for ref in wanted:
        model, _, name = ref.partition(":")
        try:
            sldb.retrack_document(store, pythonpath, model, name, paths[ref], ACTOR)
            retracked.append(ref)
        except (sldb.SldbFailure, KeyError) as error:
            failed.append(f"{ref}: {error}")
    if retracked:
        sldb.refresh_store_indexes(store, pythonpath)
    unchanged = sorted(set(refs or []) - set(stale))
    return RetrackReport(retracked=retracked, unchanged=unchanged, failed=failed)
