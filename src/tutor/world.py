"""Fachada delgada sobre `kb.KnowledgeBase` para la KB del tutor APOS.

Es lo que usan el chat, el MCP y el benchmark; no reimplementa nada de `kb`: abre la KB,
elige el embedder que `kb.yaml` declara y traduce documentos a `dict`s planos.

    from tutor import world
    kb = world.open_kb()                      # TUTOR_KB o kbs/apos; construye el store si falta
    world.list_atoms(kb)                      # [{id, title, tags, summary, parent, question, model}]
    world.children(kb, "branch-apos-core-structures-action")
    world.rank(kb, "qué es encapsulación", k=5)   # [(id, score)]
    world.role_projection(kb, "tutor")        # kb.Projection
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from kb import KnowledgeBase, Projection, load_manifest

from tutor.embedding import ENV_VAR, get_embedder

log = logging.getLogger(__name__)

ENV_KB = "TUTOR_KB"
DEFAULT_ROOT = Path("kbs") / "apos"
KNOWLEDGE_MODEL = "KnowledgeAtom"
BRANCH_MODEL = "BranchNode"
RELATION = "child_of"
STORE_DIR = ".sldb"
_ATOMS_DIR = Path("desk") / "atoms"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def kb_root_default() -> Path:
    """`TUTOR_KB` si está definida; si no, `kbs/apos` del repo."""
    env = os.environ.get(ENV_KB)
    return Path(env).expanduser().resolve() if env else (repo_root() / DEFAULT_ROOT).resolve()


def open_kb(root: Path | None = None, embedder: Any | None = None, *, build_if_missing: bool = True) -> KnowledgeBase:
    """Abre (y valida) la KB. Sin `embedder`, usa el que pide `TUTOR_EMBEDDER` o, si no, el que
    declara `kb.yaml` (`hash:char-ngram-256` por defecto). Si no hay store `.sldb/` y
    `build_if_missing`, lo genera con `tutor.kb_build` desde `desk/atoms/`."""
    root = (root or kb_root_default()).resolve()
    if build_if_missing and not (root / STORE_DIR).is_dir():
        _build(root)
    if embedder is None:
        embedder = get_embedder(os.environ.get(ENV_VAR) or _declared_embedder(root))
    return KnowledgeBase.open(root, embedder)


def list_atoms(kb: KnowledgeBase) -> list[dict[str, Any]]:
    """Todos los átomos de conocimiento (KnowledgeAtom y subclases), ordenados por id."""
    return [atom_dict(d) for d in kb.by_model(KNOWLEDGE_MODEL)]


def list_branches(kb: KnowledgeBase) -> list[dict[str, Any]]:
    """Todas las ramas de la taxonomía, ordenadas por id."""
    return [atom_dict(d) for d in kb.by_model(BRANCH_MODEL)]


def get_atom(kb: KnowledgeBase, atom_id: str) -> dict[str, Any] | None:
    """Un átomo o rama por id (`Modelo:nombre` también vale); None si no existe."""
    try:
        return atom_dict(kb.get(atom_id))
    except KeyError:
        return None


def children(kb: KnowledgeBase, atom_id: str) -> list[dict[str, Any]]:
    """Los hijos directos de una rama (átomos y ramas), por las aristas `child_of`."""
    name = _name(atom_id)
    refs = [r.source_ref for r in kb.relations(RELATION) if _name(r.target_ref) == name]
    return [atom_dict(kb.get(ref)) for ref in refs]


def parent(kb: KnowledgeBase, atom_id: str) -> dict[str, Any] | None:
    """La rama padre de un átomo o rama; None en la raíz o si no existe."""
    name = _name(atom_id)
    for relation in kb.relations(RELATION):
        if _name(relation.source_ref) == name:
            return atom_dict(kb.get(relation.target_ref))
    return None


def rank(kb: KnowledgeBase, query: str, k: int = 10, *, threshold: float = 0.0) -> list[tuple[str, float]]:
    """Los `k` átomos más parecidos a `query`, como `(id, score)`, de mejor a peor."""
    return [(hit.name, hit.score) for hit in kb.rank(query, k, threshold=threshold)]


def role_projection(kb: KnowledgeBase, role: str = "tutor") -> Projection:
    """La `ProjectionDoc` del rol: qué modelos y relaciones ve."""
    return kb.projection(role)


def agent(kb: KnowledgeBase, role: str = "tutor") -> dict[str, Any] | None:
    """El `AgentDoc` del rol (persona en `framing`, normas en `instructions`); None si no hay."""
    for document in kb.by_model("AgentDoc"):
        if document.payload.get("role") == role:
            return {"id": document.name, **document.payload}
    return None


def atom_dict(document: Any) -> dict[str, Any]:
    """La vista plana de un documento: id, title, tags, summary, parent, question, model (+ el payload)."""
    payload = dict(document.payload)
    summary = payload.get("answer") or payload.get("description") or payload.get("summary") or ""
    return {
        "id": document.name,
        "title": payload.get("title", document.name),
        "tags": list(document.tags),
        "summary": summary,
        "parent": payload.get("parent"),
        "question": payload.get("five_wh_one_plus"),
        "model": document.model,
        "provenance": payload.get("provenance"),
        "path": document.path,
    }


def _name(ref: str) -> str:
    return ref.rpartition(":")[2]


def _declared_embedder(root: Path) -> str | None:
    manifest, _ = load_manifest(root)
    return manifest.index.embedder_id if manifest is not None and manifest.index is not None else None


def _build(root: Path) -> None:
    from tutor.kb_build import build

    atoms = repo_root() / _ATOMS_DIR
    log.warning("no hay store en %s: generándolo desde %s", root, atoms)
    report = build(atoms, root, pack_dir=_pack_dir(), embedder_name=os.environ.get(ENV_VAR), index=True)
    if not report.is_valid:
        raise RuntimeError("la KB generada no valida:\n" + "\n".join(e.line() for e in report.errors))


def _pack_dir() -> Path | None:
    pack = repo_root() / "apps" / "kb_agent" / "packs" / "apos"
    return pack if pack.is_dir() else None


__all__ = [
    "agent",
    "atom_dict",
    "children",
    "get_atom",
    "kb_root_default",
    "list_atoms",
    "list_branches",
    "open_kb",
    "parent",
    "rank",
    "role_projection",
]
