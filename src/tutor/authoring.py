"""Capa de escritura sobre las KBs sldb del tutor: crear, poblar, enlazar, validar, reconstruir.

Sin MCP ni LLM: funciones puras de efectos sobre disco, testeables solas, que `tutor.mcp_server`
expone como tools. Reutiliza los constructores de documentos de `tutor.kb_build` (relación
`child_of`, categorías, `AgentDoc`, `ProjectionDoc`, manifiesto) y escribe con la API pública
de sldb (`create_document`, `save_document_payload`, `delete_document`, `update_store_indexes`,
`rebuild_edges`); lee y valida con `kb.KnowledgeBase`.

    from tutor import authoring
    authoring.create_kb("demo", "KB de prueba")                      # TUTOR_KBS_ROOT/demo
    authoring.upsert_atom("demo", {"title": "...", "question": "what", "answer": "...",
                                   "provenance": "...", "tags": ["topic:x"], "parent": "branch-demo"})
    authoring.validate_kb("demo")["ok"]

Raíz de KBs: `TUTOR_KBS_ROOT` (default `kbs/` del repo); cada KB es `<root>/<kb_id>/kb.yaml`.
Todo lo que recibe se valida con los modelos Pydantic de `kb_models` antes de escribir, y todo
lo que devuelve son dicts serializables. Los errores de uso son `AuthoringError(message, hint)`.

Rutas absolutas: igual que `kb_build`, el store se arma con `root.resolve()` y un `pythonpath`
resuelto; `.sldb/core/store_index.yaml` queda con rutas de esta máquina y por eso es derivado
(`rebuild_kb` lo regenera desde los `.md`).
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from tutor import kb_build, world
from tutor.embedding import get_embedder

log = logging.getLogger(__name__)

ENV_ROOT = "TUTOR_KBS_ROOT"
ACTOR = "tutor authoring"
RELATION = kb_build.RELATION
MODEL_REFS = (
    *kb_build.MODEL_REFS,
    f"{kb_build.MODELS_PACKAGE}.ingest:SourceDoc",
    f"{kb_build.MODELS_PACKAGE}.ingest:SourceChunk",
)
#: Carpeta (relativa a la raíz de la KB) donde vive cada modelo; también sirve para inferir el
#: modelo de un `.md` al reconstruir un store perdido.
FOLDERS: dict[str, str] = {
    "KnowledgeAtom": "knowledge",
    "SourceAtom": "sources",
    "BranchNode": "taxonomy",
    "RelationDoc": "relations",
    "RelationTypeDoc": "kgdb/relation_types",
    "TagNamespaceDoc": "categories",
    "AgentDoc": "agent",
    "ProjectionDoc": "projections",
    "SourceDoc": "ingest/sources",
    "SourceChunk": "ingest/chunks",
}
KB_ID = re.compile(r"^[a-z][a-z0-9-]*$")
IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
RELATION_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
QUESTIONS = ("what", "why", "how", "how_not", "when", "where", "for_whom")
SLUG_MAX = 72
#: Namespaces de tags que toda KB nueva declara (`categories: required` exige describir cada uno).
DEFAULT_NAMESPACES: dict[str, dict[str, Any]] = {
    "system": {
        "meaning": "A qué sistema o base de conocimiento pertenece el documento.",
        "use_when": "Siempre: todo átomo y rama lleva system:<kb>.",
        "do_not_use_when": "Para describir el tema: usa topic.",
        "examples": [],
    },
    "topic": {
        "meaning": "El concepto o tema principal del que habla el átomo.",
        "use_when": "El átomo trata ese concepto de forma central.",
        "do_not_use_when": "El concepto solo se menciona de paso.",
        "examples": ["topic:ejemplo"],
    },
    "layer": {
        "meaning": "Capa discursiva del átomo: teoría, pedagogía, ejemplo, fuente.",
        "use_when": "Quieres distinguir el tipo de contenido más allá del tema.",
        "do_not_use_when": "El dato ya lo dice topic.",
        "examples": ["layer:theory", "layer:pedagogy", "layer:example"],
    },
    **kb_build.EXTRA_NAMESPACES,
}
DEFAULT_FRAMING = (
    "Eres un tutor experto en {title}. Ayudas a estudiantes y docentes a entender el tema con "
    "explicaciones claras, concretas y fieles a las fuentes."
)
DEFAULT_INSTRUCTIONS = kb_build.DEFAULT_POLICY
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.M)


class AuthoringError(Exception):
    """Un error de uso (no un bug): qué pasó y qué hacer."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def to_dict(self) -> dict[str, str]:
        return {"error": self.message, "hint": self.hint}


# -- raíz y rutas -----------------------------------------------------------------------


def kbs_root(root: Path | str | None = None) -> Path:
    """`root` si viene; si no, `TUTOR_KBS_ROOT`; si no, `kbs/` del repo."""
    if root is not None:
        return Path(root).expanduser().resolve()
    env = os.environ.get(ENV_ROOT)
    return Path(env).expanduser().resolve() if env else (world.repo_root() / "kbs").resolve()


def kb_path(kb_id: str, root: Path | str | None = None, *, must_exist: bool = True) -> Path:
    """La carpeta de la KB; `AuthoringError` si el id es inválido o (con `must_exist`) no existe."""
    if not KB_ID.match(kb_id):
        raise AuthoringError(f"kb_id inválido: {kb_id!r}", "usa minúsculas, dígitos y guiones, empezando por letra")
    path = kbs_root(root) / kb_id
    if must_exist and not (path / "kb.yaml").is_file():
        raise AuthoringError(f"no existe la KB {kb_id!r} en {path.parent}", "créala con create_kb o revisa TUTOR_KBS_ROOT")
    return path


def models_pythonpath(path: Path) -> str:
    """El `pythonpath` de `kb.yaml`: `..` si la KB vive en `kbs/` del repo (donde está `kb_models`),
    si no la ruta absoluta de ese `kbs/`."""
    repo_kbs = (world.repo_root() / "kbs").resolve()
    return ".." if path.resolve().parent == repo_kbs else str(repo_kbs)


def slugify(text: str, prefix: str = "") -> str:
    """`'La Acción, en APOS'` → `'la-accion-en-apos'` (ascii, minúsculas, guiones), con prefijo."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")[:SLUG_MAX].strip("-")
    if not slug:
        raise AuthoringError(f"no se puede derivar un id de {text!r}", "pasa un id explícito")
    return f"{prefix}{slug}" if prefix and not slug.startswith(prefix) else slug


def demote_headings(text: str) -> str:
    """sldb no admite encabezados dentro de un campo: `## Título` → `**Título**`."""
    return HEADING.sub(r"**\1**", text.strip())


# -- el escritor: una KB abierta para escribir ------------------------------------------


@dataclass
class KbWriter:
    """Una KB y su store, con las operaciones de escritura de sldb y la lectura vía `kb`."""

    root: Path
    _kb: Any = None
    _report: Any = None

    @classmethod
    def open(cls, kb_id: str, root: Path | str | None = None) -> KbWriter:
        return cls(kb_path(kb_id, root))

    @property
    def store(self) -> Path:
        return self.root / world.STORE_DIR

    @property
    def pythonpath(self) -> str:
        manifest = yaml.safe_load((self.root / "kb.yaml").read_text(encoding="utf-8")) or {}
        return str((self.root / str((manifest.get("kb") or {}).get("pythonpath") or ".")).resolve())

    @property
    def kb_id(self) -> str:
        return self.root.name

    # lectura ------------------------------------------------------------------------

    def kb(self, *, embedder: Any | None = None):
        """La KB abierta con `kb` sin bloquear por errores (se cachea hasta la próxima escritura)."""
        if self._kb is None:
            self._kb, self._report = kb_build.validate(self.root, embedder or self.embedder())
        return self._kb

    def report(self):
        self.kb()
        return self._report

    def embedder(self) -> Any:
        return get_embedder(os.environ.get(world.ENV_VAR) or world._declared_embedder(self.root))

    def find(self, name: str) -> Any | None:
        """El documento con ese nombre (o `Modelo:nombre`), o None."""
        try:
            return self.kb().get(name)
        except KeyError:
            return None

    def require(self, name: str, what: str = "documento") -> Any:
        document = self.find(name)
        if document is None:
            raise AuthoringError(f"no existe el {what} {name!r} en la KB {self.kb_id!r}", "revisa el id con list_branches o search_atoms")
        return document

    def registered_models(self) -> set[str]:
        index = yaml.safe_load((self.store / "core" / "store_index.yaml").read_text(encoding="utf-8")) or {}
        return {str(m["name"]) for m in index.get("models") or []}

    # escritura ----------------------------------------------------------------------

    def invalidate(self) -> None:
        self._kb = self._report = None

    def ensure_model(self, model: str) -> None:
        """Registra el modelo en el store si una KB vieja no lo tiene (p. ej. SourceDoc)."""
        if model in self.registered_models():
            return
        from sldb.api import add_model

        ref = next((r for r in MODEL_REFS if r.endswith(f":{model}")), None)
        if ref is None:
            raise AuthoringError(f"modelo desconocido: {model}", f"los modelos de la KB son {', '.join(FOLDERS)}")
        add_model(self.store, ref, pythonpath=self.pythonpath, actor=ACTOR)
        self.invalidate()

    def write(self, doc: kb_build.Doc) -> None:
        """Crea el documento o, si ya existe con ese nombre, reemplaza su contenido."""
        from sldb.api import create_document, save_document_payload

        self.ensure_model(doc.model)
        existing = self.find(doc.doc_name)
        if existing is not None:
            if existing.model != doc.model:
                raise AuthoringError(
                    f"{doc.doc_name!r} ya existe como {existing.model}, no como {doc.model}",
                    "borra el documento viejo o usa otro id",
                )
            save_document_payload(self.store, doc.model, doc.doc_name, doc.payload, pythonpath=self.pythonpath, actor=ACTOR)
        else:
            create_document(self.store, doc.model, self.root / doc.path, doc.payload, name=doc.doc_name, pythonpath=self.pythonpath, actor=ACTOR)
        self.invalidate()

    def delete(self, name: str) -> None:
        from sldb.api import delete_document

        delete_document(self.store, name, pythonpath=self.pythonpath, actor=ACTOR)
        self.invalidate()

    def refresh(self, *, index: bool = True) -> dict[str, Any]:
        """Índices derivados de sldb (hashes, aristas) y, con `index`, el índice de embeddings."""
        from sldb.api import rebuild_edges, update_store_indexes

        update_store_indexes(self.store, pythonpath=self.pythonpath, wait=True)
        rebuild_edges(self.store, pythonpath=self.pythonpath, wait=True)
        self.invalidate()
        counts: dict[str, Any] = {}
        if index:
            counts = dict(self.kb().refresh_index().counts)
            self.invalidate()
        return counts

    # relaciones ---------------------------------------------------------------------

    def relations_of(self, name: str, relation: str | None = None) -> list[Any]:
        """Los `RelationDoc` en que `name` es origen o destino (de un tipo, o de todos)."""
        found = []
        for document in self.kb().by_model("RelationDoc"):
            payload = document.payload
            if relation is not None and payload.get("relation_type") != relation:
                continue
            endpoints = {str(payload.get("source_id", "")).rpartition(":")[2], str(payload.get("target_id", "")).rpartition(":")[2]}
            if name in endpoints:
                found.append(document)
        return found

    def relation_types(self) -> dict[str, Any]:
        return {str(d.payload.get("name")): d for d in self.kb().by_model("RelationTypeDoc")}


# -- KBs ----------------------------------------------------------------------------------


def list_kbs(root: Path | str | None = None) -> list[dict[str, Any]]:
    """Las KBs bajo la raíz: `[{kb_id, path, n_atoms, n_branches, roles, valid}]`."""
    base = kbs_root(root)
    found: list[dict[str, Any]] = []
    for path in sorted(p for p in base.iterdir() if (p / "kb.yaml").is_file()) if base.is_dir() else []:
        found.append(kb_info(path.name, root))
    return found


def kb_info(kb_id: str, root: Path | str | None = None) -> dict[str, Any]:
    """Resumen de una KB: conteos, roles con `AgentDoc`, si valida, fuentes ingeridas."""
    writer = KbWriter.open(kb_id, root)
    info: dict[str, Any] = {"kb_id": kb_id, "path": str(writer.root)}
    if not writer.store.is_dir():
        return {**info, "n_atoms": 0, "n_branches": 0, "roles": [], "valid": False, "error": "sin store .sldb/ (usa rebuild_kb)"}
    try:
        kb = writer.kb()
    except Exception as error:  # KnowledgeBaseInvalid bloqueante, modelos que no importan…
        return {**info, "n_atoms": 0, "n_branches": 0, "roles": [], "valid": False, "error": str(error)}
    stats = kb.stats()
    return {
        **info,
        "title": str((world.agent(kb) or {}).get("title") or kb.name),
        "n_atoms": len(kb.by_model(world.KNOWLEDGE_MODEL)),
        "n_branches": len(kb.by_model(world.BRANCH_MODEL)),
        "n_sources": len(kb.by_model("SourceDoc")) if "SourceDoc" in writer.registered_models() else 0,
        "roles": sorted(str(d.payload.get("role")) for d in kb.by_model("AgentDoc")),
        "relations": dict(stats.relations_by_type),
        "valid": writer.report().is_valid,
        "n_errors": len(writer.report().errors),
        "embedder_id": world._declared_embedder(writer.root),
    }


def create_kb(
    kb_id: str,
    title: str,
    language: str = "es",
    description: str = "",
    *,
    root: Path | str | None = None,
    embedder_name: str | None = None,
    role: str = "tutor",
) -> dict[str, Any]:
    """Crea una KB vacía pero válida para `kb`: `kb.yaml`, `tag-namespaces.yaml`, categorías por
    defecto, tipo de relación `child_of`, rama raíz `branch-<kb_id>`, `projection-<role>`,
    `agent-<role>-<kb_id>` con encuadre e instrucciones por defecto, y el store sldb."""
    path = kb_path(kb_id, root, must_exist=False)
    if (path / "kb.yaml").exists():
        raise AuthoringError(f"la KB {kb_id!r} ya existe en {path}", "usa otro kb_id o escribe sobre ella con upsert_*")
    embedder = get_embedder(embedder_name or os.environ.get(world.ENV_VAR))
    manifest = kb_build.manifest(embedder.id())
    manifest["kb"]["name"] = kb_id
    manifest["kb"]["pythonpath"] = models_pythonpath(path)
    manifest["kb"]["materialize"] = {"order": ["knowledge", "sources", "taxonomy", "ingest"]}
    namespaces = {ns: {**spec, "examples": list(spec["examples"]) or [f"{ns}:{kb_id}"]} for ns, spec in DEFAULT_NAMESPACES.items()}
    namespaces["system"]["examples"] = [f"system:{kb_id}"]
    plan = kb_build.BuildPlan(manifest=manifest, namespaces=namespaces)
    root_branch = f"branch-{kb_id}"
    plan.docs.append(
        kb_build.Doc(
            "BranchNode",
            f"{FOLDERS['BranchNode']}/{root_branch}.md",
            {
                "id": root_branch,
                "title": title,
                "tags": [f"system:{kb_id}", "node:branch"],
                "parent": None,
                "description": demote_headings(description) or f"Rama raíz de la KB «{title}»: de aquí cuelgan todas las ramas y átomos.",
                "provenance": "Creada por `tutor.authoring.create_kb`.",
            },
        )
    )
    plan.docs.append(_relation_type_doc(RELATION, child_of=True))
    plan.docs.extend(kb_build.category_doc(ns, spec) for ns, spec in sorted(namespaces.items()))
    plan.docs.append(_agent_doc(kb_id, role, DEFAULT_FRAMING.format(title=title), DEFAULT_INSTRUCTIONS, f"Tutor de {title}", language))
    plan.docs.append(_projection_doc(role))
    try:
        _write_plan(path, plan, MODEL_REFS)
    except Exception:
        shutil.rmtree(path, ignore_errors=True)
        raise
    writer = KbWriter(path)
    writer.refresh()
    return {**kb_info(kb_id, root), "root_branch": root_branch, "agent": f"agent-{role}-{kb_id}", "language": language}


def _write_plan(path: Path, plan: kb_build.BuildPlan, refs: tuple[str, ...]) -> None:
    """Como `kb_build.write_kb`, pero sin borrar lo que hubiera y registrando también los modelos de ingesta."""
    from sldb.api import add_model, create_document, init_relations, init_store

    path.mkdir(parents=True, exist_ok=True)
    (path / "kb.yaml").write_text(
        "# Lo que esta KB declara de sí misma (contrato kb_version 1, lo lee runtime/kb).\n"
        "# Creado por `tutor.authoring`; `rebuild_kb` regenera el store .sldb/ a partir de los .md.\n"
        + yaml.safe_dump(plan.manifest, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    _write_namespaces(path, plan.namespaces)
    pythonpath = str((path / plan.manifest["kb"]["pythonpath"]).resolve())
    store = init_store(path, force=True).store_path
    init_relations(store, pythonpath)
    for ref in refs:
        add_model(store, ref, pythonpath=pythonpath, actor=ACTOR)
    for doc in plan.docs:
        create_document(store, doc.model, path / doc.path, doc.payload, name=doc.doc_name, pythonpath=pythonpath, actor=ACTOR)


def _write_namespaces(path: Path, namespaces: dict[str, dict[str, Any]]) -> None:
    (path / "tag-namespaces.yaml").write_text(
        "# Taxonomía de tags de esta KB: un namespace por categoría; el tag se escribe `ns:valor`.\n"
        + yaml.safe_dump({"namespaces": namespaces}, sort_keys=True, allow_unicode=True),
        encoding="utf-8",
    )


def validate_kb(kb_id: str, root: Path | str | None = None) -> dict[str, Any]:
    """La validación real de `kb` (V0–V13): `{ok, errors[], warnings[], stats}`."""
    writer = KbWriter.open(kb_id, root)
    if not writer.store.is_dir():
        return {"ok": False, "errors": [{"rule": "V1", "origin": "kb", "doc": None, "path": "", "message": "no hay store .sldb/"}], "warnings": [], "stats": {}, "hint": "corre rebuild_kb"}
    try:
        kb = writer.kb()
    except Exception as error:
        report = getattr(error, "report", None)
        errors = [e.model_dump() for e in report.errors] if report is not None else [{"rule": "V1", "origin": "kb", "doc": None, "path": "", "message": str(error)}]
        return {"ok": False, "errors": errors, "warnings": [], "stats": {}, "hint": "corre rebuild_kb; si persiste, revisa los .md que nombra"}
    report = writer.report()
    warnings: list[str] = []
    try:
        audit = kb.audit_index()
        warnings += [f"índice: sin vector {name}" for name in audit.missing]
        warnings += [f"índice: vector desactualizado {name}" for name in audit.stale]
        warnings += [f"índice: vector huérfano {name}" for name in audit.orphan]
    except Exception as error:  # índice no declarado o embedder distinto
        warnings.append(f"índice: {error}")
    for document in kb.by_model(world.KNOWLEDGE_MODEL) + kb.by_model(world.BRANCH_MODEL):
        parent = document.payload.get("parent")
        if parent and writer.find(str(parent)) is None:
            warnings.append(f"{document.name}: parent {parent!r} no existe")
    stats = kb.stats()
    return {
        "ok": report.is_valid,
        "errors": [e.model_dump() for e in report.errors],
        "warnings": warnings,
        "stats": {"documents": stats.documents, "eligible": stats.eligible, "by_model": stats.by_model, "relations_by_type": stats.relations_by_type},
    }


def rebuild_kb(kb_id: str, root: Path | str | None = None) -> dict[str, Any]:
    """Rehace `.sldb/` desde cero a partir de los `.md` (modelos, documentos, aristas) y el índice de
    embeddings. Sirve tras clonar/mover la KB (el store lleva rutas absolutas) o si quedó inconsistente."""
    from sldb.api import track_document_file

    writer = KbWriter.open(kb_id, root)
    root_path = writer.root
    known: dict[str, str] = {}  # ruta relativa → modelo, según el store viejo si lo hay
    if writer.store.is_dir():
        try:
            known = {d.path: d.model for d in writer.kb().documents()}
        except Exception as error:
            log.warning("store previo ilegible, se infiere el modelo por carpeta: %s", error)
    manifest = yaml.safe_load((root_path / "kb.yaml").read_text(encoding="utf-8")) or {}
    pythonpath = str((root_path / str((manifest.get("kb") or {}).get("pythonpath") or ".")).resolve())
    shutil.rmtree(writer.store, ignore_errors=True)
    _write_store(root_path, pythonpath, MODEL_REFS)
    tracked: dict[str, int] = {}
    skipped: list[str] = []
    for path in sorted(root_path.rglob("*.md")):
        relative = path.relative_to(root_path).as_posix()
        if relative.startswith(("sldb/", ".sldb/")):
            continue
        model = known.get(relative) or _model_for_path(relative)
        if model is None:
            skipped.append(relative)
            continue
        track_document_file(writer.store, model, path, pythonpath=pythonpath, actor=ACTOR)
        tracked[model] = tracked.get(model, 0) + 1
    counts = writer.refresh()
    return {"kb_id": kb_id, "tracked": tracked, "skipped": skipped, "index": counts, **validate_kb(kb_id, root)}


def _write_store(path: Path, pythonpath: str, refs: tuple[str, ...]) -> None:
    from sldb.api import add_model, init_relations, init_store

    store = init_store(path, force=True).store_path
    init_relations(store, pythonpath)
    for ref in refs:
        add_model(store, ref, pythonpath=pythonpath, actor=ACTOR)


def _model_for_path(relative: str) -> str | None:
    for model, folder in sorted(FOLDERS.items(), key=lambda kv: -len(kv[1])):
        if relative.startswith(folder + "/"):
            return model
    return None


# -- átomos y ramas -----------------------------------------------------------------------


def upsert_atom(kb_id: str, atom: dict[str, Any], root: Path | str | None = None) -> dict[str, Any]:
    """Crea o actualiza un `KnowledgeAtom`: `{id?, title, question, answer, provenance, tags, parent}`.
    Sin `id` lo deriva del título (`atom-<slug>`); `parent` debe existir (rama o átomo). Escribe el
    `.md`, la relación `child_of`, declara los namespaces de tag que falten y refresca índices."""
    from kb_models import KnowledgeAtom

    writer = KbWriter.open(kb_id, root)
    data = dict(atom)
    title = str(data.get("title") or "").strip()
    if not title:
        raise AuthoringError("el átomo necesita title", "un título corto que afirme una sola cosa")
    atom_id = str(data.get("id") or slugify(title, "atom-")).strip()
    _check_identifier(atom_id, "id del átomo")
    question = str(data.get("question") or data.get("five_wh_one_plus") or "what").strip().lower()
    if question not in QUESTIONS:
        raise AuthoringError(f"question inválida: {question!r}", f"una de {', '.join(QUESTIONS)}")
    parent = str(data.get("parent") or "").strip() or None
    if parent is None:
        raise AuthoringError("el átomo necesita parent", f"usa la rama raíz branch-{kb_id} o una de list_branches")
    if parent == atom_id:
        raise AuthoringError("un átomo no puede ser su propio parent", "elige una rama")
    parent_doc = writer.require(parent, "parent (rama o átomo)")
    tags = [str(t).strip() for t in data.get("tags") or [] if str(t).strip()]
    payload = {
        "id": atom_id,
        "title": title,
        "five_wh_one_plus": question,
        "tags": tags,
        "parent": parent,
        "answer": demote_headings(str(data.get("answer") or "")),
        "provenance": demote_headings(str(data.get("provenance") or "")),
    }
    if not payload["answer"]:
        raise AuthoringError("el átomo necesita answer", "la respuesta curada a la pregunta, una afirmación")
    if not payload["provenance"]:
        raise AuthoringError("el átomo necesita provenance", "fuente y sección, o el chunk_id de ingest_text del que sale")
    _validate(KnowledgeAtom, payload, "átomo")
    existing = writer.find(atom_id)
    if existing is not None and not existing.is_a(world.KNOWLEDGE_MODEL):
        raise AuthoringError(f"{atom_id!r} ya existe como {existing.model}", "usa otro id o upsert_branch")
    model = existing.model if existing is not None else "KnowledgeAtom"
    path = existing.path if existing is not None else f"{FOLDERS['KnowledgeAtom']}/{atom_id}.md"
    declared = _ensure_namespaces(writer, tags, atom_id)
    writer.write(kb_build.Doc(model, path, payload, name=atom_id))
    _set_parent(writer, model, atom_id, parent_doc)
    writer.refresh()
    result = world.get_atom(writer.kb(), atom_id) or {}
    return {**result, "created": existing is None, "declared_namespaces": declared}


def upsert_branch(kb_id: str, branch: dict[str, Any], root: Path | str | None = None) -> dict[str, Any]:
    """Crea o actualiza un `BranchNode`: `{id?, title, parent, summary, tags?}`. Sin `id` lo deriva del
    título (`branch-<slug>`); `parent` debe ser una rama existente (None solo para la raíz)."""
    from kb_models import BranchNode

    writer = KbWriter.open(kb_id, root)
    data = dict(branch)
    title = str(data.get("title") or "").strip()
    if not title:
        raise AuthoringError("la rama necesita title", "el nombre de la rama")
    branch_id = str(data.get("id") or slugify(title, "branch-")).strip()
    _check_identifier(branch_id, "id de la rama")
    parent = str(data.get("parent") or "").strip() or None
    existing = writer.find(branch_id)
    if existing is not None and existing.model != world.BRANCH_MODEL:
        raise AuthoringError(f"{branch_id!r} ya existe como {existing.model}", "usa otro id o upsert_atom")
    if parent is None and not (existing is not None and existing.payload.get("parent") is None):
        raise AuthoringError("la rama necesita parent", f"usa la rama raíz branch-{kb_id} o una de list_branches")
    if parent == branch_id:
        raise AuthoringError("una rama no puede ser su propio parent", "elige otra rama")
    parent_doc = None
    if parent is not None:
        parent_doc = writer.require(parent, "parent (rama)")
        if parent_doc.model != world.BRANCH_MODEL:
            raise AuthoringError(f"el parent de una rama debe ser una rama; {parent!r} es {parent_doc.model}", "usa list_branches")
        if _descends_from(writer, parent, branch_id):
            raise AuthoringError(f"{parent!r} desciende de {branch_id!r}: haría un ciclo", "elige otra rama")
    tags = [str(t).strip() for t in data.get("tags") or [f"system:{kb_id}", "node:branch"] if str(t).strip()]
    payload = {
        "id": branch_id,
        "title": title,
        "tags": tags,
        "parent": parent,
        "description": demote_headings(str(data.get("summary") or data.get("description") or "")) or f"Rama «{title}».",
        "provenance": demote_headings(str(data.get("provenance") or "Creada por `tutor.authoring.upsert_branch`.")),
    }
    _validate(BranchNode, payload, "rama")
    declared = _ensure_namespaces(writer, tags, branch_id)
    writer.write(kb_build.Doc(world.BRANCH_MODEL, existing.path if existing else f"{FOLDERS['BranchNode']}/{branch_id}.md", payload, name=branch_id))
    if parent_doc is not None:
        _set_parent(writer, world.BRANCH_MODEL, branch_id, parent_doc)
    writer.refresh(index=False)
    result = world.get_atom(writer.kb(), branch_id) or {}
    return {**result, "created": existing is None, "declared_namespaces": declared}


def delete_atom(kb_id: str, atom_id: str, root: Path | str | None = None) -> dict[str, Any]:
    """Borra un átomo o rama: su `.md`, todas las relaciones en que participa y el índice. Una rama
    con hijos no se borra (muévelos antes)."""
    writer = KbWriter.open(kb_id, root)
    document = writer.require(atom_id, "átomo o rama")
    if document.model == world.BRANCH_MODEL:
        kids = world.children(writer.kb(), atom_id)
        if kids:
            raise AuthoringError(f"la rama {atom_id!r} tiene {len(kids)} hijos", "reasigna su parent con upsert_atom/upsert_branch antes de borrarla")
    removed = [d.name for d in writer.relations_of(document.name)]
    for name in removed:
        writer.delete(name)
    writer.delete(document.name)
    writer.refresh()
    return {"deleted": document.name, "model": document.model, "relations_removed": removed}


def link_atoms(kb_id: str, source: str, relation: str, target: str, *, description: str = "", root: Path | str | None = None) -> dict[str, Any]:
    """Una relación tipada `source --relation--> target` entre documentos existentes. Si el tipo no
    está declarado lo declara (`RelationTypeDoc` dirigido, many_to_many) con los modelos de ambos."""
    writer = KbWriter.open(kb_id, root)
    if not RELATION_NAME.match(relation):
        raise AuthoringError(f"nombre de relación inválido: {relation!r}", "minúsculas y guion bajo, p. ej. requires, contrasts_with")
    source_doc = writer.require(source, "origen")
    target_doc = writer.require(target, "destino")
    if source_doc.name == target_doc.name:
        raise AuthoringError("origen y destino son el mismo documento", "elige dos documentos distintos")
    types = writer.relation_types()
    declared = relation not in types
    if declared:
        writer.write(_relation_type_doc(relation, description=description, source_types=[source_doc.model], target_types=[target_doc.model]))
    else:
        type_doc = types[relation]
        sources = [str(t) for t in type_doc.payload.get("source_types") or []]
        targets = [str(t) for t in type_doc.payload.get("target_types") or []]
        if (sources and not any(source_doc.is_a(t) for t in sources)) or (targets and not any(target_doc.is_a(t) for t in targets)):
            raise AuthoringError(
                f"{relation} une {sources} → {targets}; recibió {source_doc.model} → {target_doc.model}",
                "usa otro tipo de relación o declara uno nuevo con otro nombre",
            )
    if relation == RELATION:
        _set_parent(writer, source_doc.model, source_doc.name, target_doc)
    else:
        writer.write(_relation_doc(relation, source_doc, target_doc))
    writer.refresh(index=False)
    return {"relation": f"{relation}--{source_doc.name}--{target_doc.name}", "source": source_doc.key, "target": target_doc.key, "type_declared": declared}


def upsert_agent(kb_id: str, role: str, framing: str, instructions: str, title: str | None = None, *, language: str = "es", root: Path | str | None = None) -> dict[str, Any]:
    """El `AgentDoc` del rol (`agent-<role>-<kb_id>`: persona en `framing`, normas en `instructions`)
    y su `ProjectionDoc` (`projection-<role>`: átomos + ramas + child_of, solo lectura)."""
    if not RELATION_NAME.match(role):
        raise AuthoringError(f"rol inválido: {role!r}", "minúsculas y guion bajo, p. ej. tutor, evaluador")
    writer = KbWriter.open(kb_id, root)
    _ensure_namespaces(writer, [f"agent:{role}"], f"agent-{role}-{kb_id}")
    writer.write(_agent_doc(kb_id, role, framing, instructions, title or f"Agente {role} de {kb_id}", language))
    writer.write(_projection_doc(role))
    writer.refresh(index=False)
    return world.agent(writer.kb(), role) or {}


def list_tutors(kb_id: str, root: Path | str | None = None) -> list[dict[str, Any]]:
    """Los roles con `AgentDoc`: `[{role, id, title, summary, projection}]`."""
    kb = KbWriter.open(kb_id, root).kb()
    return [
        {"role": str(d.payload.get("role")), "id": d.name, "title": str(d.payload.get("title") or d.name), "summary": str(d.payload.get("summary") or ""), "projection": str(d.payload.get("projection") or "all")}
        for d in kb.by_model("AgentDoc")
    ]


# -- helpers --------------------------------------------------------------------------------


def _validate(model: type, payload: dict[str, Any], what: str) -> None:
    from pydantic import ValidationError

    try:
        model.model_validate(payload)
    except ValidationError as error:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors())
        raise AuthoringError(f"{what} inválido: {problems}", "los tags van como namespace:valor en minúsculas; question es una de 5W1H+") from None


def _check_identifier(value: str, what: str) -> None:
    if not IDENTIFIER.match(value):
        raise AuthoringError(f"{what} inválido: {value!r}", "minúsculas, dígitos, guion y guion bajo (norma de identificadores)")


def _ensure_namespaces(writer: KbWriter, tags: list[str], who: str) -> list[str]:
    """Declara (`TagNamespaceDoc` + `tag-namespaces.yaml`) los namespaces de `tags` que la KB no tiene."""
    declared = {str(d.payload.get("tag")) for d in writer.kb().by_model("TagNamespaceDoc")}
    added: list[str] = []
    for namespace in sorted({t.partition(":")[0] for t in tags if ":" in t} - declared):
        spec = DEFAULT_NAMESPACES.get(namespace) or {
            "meaning": f"Namespace `{namespace}` (declarado automáticamente al etiquetar `{who}`).",
            "use_when": f"Tags {namespace}:<valor> como los de `{who}`.",
            "do_not_use_when": "Cuando otro namespace ya expresa lo mismo.",
            "examples": [t for t in tags if t.startswith(f"{namespace}:")][:3],
        }
        writer.write(kb_build.category_doc(namespace, spec))
        added.append(namespace)
    if added:
        path = writer.root / "tag-namespaces.yaml"
        current = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("namespaces") or {} if path.is_file() else {}
        for namespace in added:
            doc = next(d for d in writer.kb().by_model("TagNamespaceDoc") if d.payload.get("tag") == namespace)
            current[namespace] = {k: doc.payload.get(k) for k in ("meaning", "use_when", "do_not_use_when", "examples")}
        _write_namespaces(writer.root, current)
    return added


def _set_parent(writer: KbWriter, model: str, name: str, parent_doc: Any) -> None:
    """Deja exactamente una relación `child_of` saliendo de `name`, hacia `parent_doc`."""
    wanted = f"{RELATION}--{name}--{parent_doc.name}"
    for relation in writer.relations_of(name, RELATION):
        if str(relation.payload.get("source_id", "")).rpartition(":")[2] == name and relation.name != wanted:
            writer.delete(relation.name)
    if writer.find(wanted) is None:
        writer.write(kb_build.relation_doc(model, name, parent_doc.model, parent_doc.name))


def _descends_from(writer: KbWriter, node: str, ancestor: str) -> bool:
    seen: set[str] = set()
    current: str | None = node
    while current and current not in seen:
        if current == ancestor:
            return True
        seen.add(current)
        parent = world.parent(writer.kb(), current)
        current = parent["id"] if parent else None
    return False


def _relation_type_doc(name: str, *, child_of: bool = False, description: str = "", source_types: list[str] | None = None, target_types: list[str] | None = None) -> kb_build.Doc:
    if child_of:
        doc = kb_build.relation_type_doc()
        doc.payload["target_types"] = ["BranchNode", "KnowledgeAtom"]
        doc.payload["description"] = (
            "El origen es un hijo del destino en la taxonomía: un átomo cuelga de una rama (o de otro "
            "átomo), una rama de otra rama. Proyección tipada del campo `parent`."
        )
        return doc
    return kb_build.Doc(
        "RelationTypeDoc",
        f"{FOLDERS['RelationTypeDoc']}/{name}.md",
        {
            "title": name,
            "name": name,
            "direction": "directed",
            "cardinality": "many_to_many",
            "axis": "WHAT",
            "source_types": source_types or [],
            "target_types": target_types or [],
            "condition": "",
            "description": demote_headings(description) or f"Relación `{name}` declarada por `tutor.authoring.link_atoms`.",
        },
    )


def _relation_doc(relation: str, source: Any, target: Any) -> kb_build.Doc:
    name = f"{relation}--{source.name}--{target.name}"
    return kb_build.Doc(
        "RelationDoc",
        f"{FOLDERS['RelationDoc']}/{name}.md",
        {"title": f"{source.name} {relation} {target.name}", "source_id": source.key, "target_id": target.key, "relation_type": relation, "condition": "", "notes": ""},
    )


def _agent_doc(kb_id: str, role: str, framing: str, instructions: str, title: str, language: str) -> kb_build.Doc:
    name = f"agent-{role}-{kb_id}"
    return kb_build.Doc(
        "AgentDoc",
        f"{FOLDERS['AgentDoc']}/{name}.md",
        {
            "id": name,
            "title": title,
            "role": role,
            "projection": role,
            "static": [{"tag": "type.knowledge.atom", "title": "Conocimiento", "render": "cited"}],
            "dynamic": ["question", "history:6"],
            "tools": [],
            "on_failure": "closed",
            "policies": ["deny_if_no_context"],
            "tags": [f"agent:{role}"],
            "provenance": f"Declarado por `tutor.authoring` (idioma: {language}).",
            "summary": f"Rol {role} de la KB {kb_id}: responde citando átomos.",
            "framing": demote_headings(framing) or DEFAULT_FRAMING.format(title=kb_id),
            "instructions": demote_headings(instructions) or DEFAULT_INSTRUCTIONS,
        },
    )


def _projection_doc(role: str) -> kb_build.Doc:
    doc = kb_build.projection_doc()
    name = f"projection-{role}"
    doc.payload["name"] = role
    doc.payload["description"] = f"Lo que ve el rol {role}: átomos de conocimiento (KnowledgeAtom y subclases) y la taxonomía (BranchNode) con sus aristas child_of, en solo lectura."
    return kb_build.Doc(doc.model, f"{FOLDERS['ProjectionDoc']}/{name}.md", doc.payload, name=name)


__all__ = [
    "AuthoringError",
    "KbWriter",
    "create_kb",
    "delete_atom",
    "kb_info",
    "kb_path",
    "kbs_root",
    "link_atoms",
    "list_kbs",
    "list_tutors",
    "rebuild_kb",
    "slugify",
    "upsert_agent",
    "upsert_atom",
    "upsert_branch",
    "validate_kb",
]
