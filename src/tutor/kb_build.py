"""Genera la KB sldb del tutor (`kbs/apos/`) a partir de los átomos Markdown de `desk/atoms/`.

    python -m tutor.kb_build --atoms desk/atoms --out kbs/apos [--embedder hash] [--no-index]

Idempotente: borra lo que generó la vez anterior (los directorios de documentos y `.sldb/`)
y lo vuelve a escribir con la API pública de sldb (`init_store`, `init_relations`,
`add_model`, `create_document`, `update_store_indexes`, `rebuild_edges`), igual que hace
`kb.portable.build_store`. Luego valida con `kb` (V0–V13) y, salvo `--no-index`, refresca el
índice de embeddings con el embedder elegido. Los `.md` que escribe son función de los
átomos fuente; el store y el índice son derivados.

Qué produce (ver `kbs/README.md`):

- `knowledge/**`, `sources/**`: un `KnowledgeAtom`/`SourceAtom` por átomo `node_type: knowledge`,
  con la misma ruta relativa que en `desk/atoms/` y el mismo `id`;
- `taxonomy/`: un `BranchNode` por átomo `node_type: branch`, más las ramas intermedias que
  los `parent_id` nombran y que no existen como archivo (marcadas en su procedencia);
- `relations/`: un `RelationDoc` `child_of--<hijo>--<padre>` por `parent_id`, con el tipo
  `child_of` declarado en `kgdb/relation_types/child_of.md`;
- `categories/`: un `TagNamespaceDoc` por namespace de tag (de `tag-namespaces.yaml` o propio);
- `agent/agent-tutor-apos.md`: el rol `tutor` (persona e instrucciones del pack `apos`);
- `projections/projection-tutor.md`: la `ProjectionDoc` de pron que el rol ve.
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("tutor.kb_build")

MODELS_PACKAGE = "kb_models"
MODEL_REFS = (
    f"{MODELS_PACKAGE}.apos:KnowledgeAtom",
    f"{MODELS_PACKAGE}.apos:SourceAtom",
    f"{MODELS_PACKAGE}.apos:BranchNode",
    f"{MODELS_PACKAGE}.governance:AgentDoc",
    f"{MODELS_PACKAGE}.kb_docs:TagNamespaceDoc",
    "pron.models:ProjectionDoc",
)
RELATION = "child_of"
ROLE = "tutor"
AGENT_NAME = f"agent-{ROLE}-apos"
PROJECTION_NAME = f"projection-{ROLE}"
ROOT_BRANCH = "branch-apos"
ACTOR = "tutor kb_build"
GENERATED_DIRS = ("knowledge", "sources", "taxonomy", "relations", "kgdb", "sldb", "categories", "agent", "projections")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)
SECTION = re.compile(r"^## (.+?)\s*$", re.M)
BRANCH_TAGS = ["system:apos", "node:branch", "layer:taxonomy"]
BRANCH_TITLES = {
    "branch-apos": "Teoría APOS",
    "branch-apos-applications": "Aplicaciones",
    "branch-apos-core-structures": "Estructuras mentales",
    "branch-apos-foundations": "Fundamentos",
    "branch-apos-genetic-decomposition": "Descomposición genética",
    "branch-apos-mathematical-domains": "Dominios matemáticos",
    "branch-apos-mechanisms": "Mecanismos",
    "branch-apos-pedagogy": "Pedagogía",
    "branch-apos-research": "Investigación",
    "branch-apos-schema-development": "Desarrollo de esquemas",
    "branch-apos-synthesis": "Síntesis",
    "branch-sources-apos-theory-book": "Libro fuente: Arnon et al. (2014)",
}
EXTRA_NAMESPACES: dict[str, dict[str, Any]] = {
    "node": {
        "meaning": "Rol estructural del documento en la taxonomía (rama).",
        "use_when": "El documento es un nodo de organización, no conocimiento.",
        "do_not_use_when": "El documento responde una pregunta sobre APOS.",
        "examples": ["node:branch"],
    },
    "agent": {
        "meaning": "Encuadre de un rol del runtime.",
        "use_when": "Declara el rol de un agente (tutor).",
        "do_not_use_when": "Describe la teoría o la taxonomía.",
        "examples": ["agent:tutor"],
    },
}
DEFAULT_PERSONA = (
    "Eres un tutor experto en APOS (Action-Process-Object-Schema), una teoría constructivista para el "
    "aprendizaje de matemáticas. Ayudas a estudiantes, investigadores y docentes a entender la teoría."
)
DEFAULT_POLICY = (
    "Responde en español usando SOLO la información de los átomos provistos. No inventes. Sé concreto. "
    "Conserva los ids atom-... cuando cites evidencia. Si la información no alcanza, dilo en una línea."
)


@dataclass(frozen=True)
class SourceAtom:
    """Un átomo tal como está en `desk/atoms/`."""

    id: str
    title: str
    question: str
    tags: list[str]
    node_type: str
    parent_id: str | None
    answer: str
    provenance: str
    relative: Path
    synthesized: bool = False


@dataclass(frozen=True)
class Doc:
    """Un documento a escribir en la KB: modelo, ruta relativa a la raíz y payload."""

    model: str
    path: str
    payload: dict[str, Any]
    name: str | None = None

    @property
    def doc_name(self) -> str:
        return self.name or Path(self.path).stem


@dataclass
class BuildPlan:
    manifest: dict[str, Any]
    namespaces: dict[str, dict[str, Any]]
    docs: list[Doc] = field(default_factory=list)


# -- leer -------------------------------------------------------------------------------


def read_atoms(atoms_dir: Path) -> list[SourceAtom]:
    """Todos los `.md` con frontmatter bajo `atoms_dir`, ordenados por id."""
    atoms: list[SourceAtom] = []
    for path in sorted(atoms_dir.rglob("*.md")):
        parsed = parse_atom(path, atoms_dir)
        if parsed is not None:
            atoms.append(parsed)
    ids = [a.id for a in atoms]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"ids repetidos en {atoms_dir}: {duplicates}")
    return sorted(atoms, key=lambda a: a.id)


def parse_atom(path: Path, atoms_dir: Path) -> SourceAtom | None:
    match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
    if match is None:
        log.warning("sin frontmatter, se omite: %s", path)
        return None
    front = yaml.safe_load(match.group(1)) or {}
    if "id" not in front or "node_type" not in front:
        log.warning("sin id o node_type, se omite: %s", path)
        return None
    sections = split_sections(match.group(2))
    return SourceAtom(
        id=str(front["id"]),
        title=str(front.get("title") or front["id"]),
        question=str(front.get("five_wh_one_plus") or "what"),
        tags=[str(t) for t in front.get("tags") or []],
        node_type=str(front["node_type"]),
        parent_id=str(front["parent_id"]) if front.get("parent_id") else None,
        answer=sections.get("Respuesta", "").strip(),
        provenance=sections.get("Procedencia", "").strip(),
        relative=path.relative_to(atoms_dir),
    )


def split_sections(body: str) -> dict[str, str]:
    """`## Título` → texto hasta el siguiente `##`."""
    sections: dict[str, str] = {}
    matches = list(SECTION.finditer(body))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[match.group(1)] = body[match.end() : end].strip()
    return sections


def synthesize_branches(atoms: list[SourceAtom]) -> list[SourceAtom]:
    """Las ramas que los `parent_id` nombran y no existen: se infieren de los ids (`a-b-c` → `a-b`)."""
    known = {a.id for a in atoms}
    missing: dict[str, SourceAtom] = {}
    pending = sorted({a.parent_id for a in atoms if a.parent_id and a.parent_id not in known})
    while pending:
        branch_id = pending.pop()
        if branch_id in known or branch_id in missing:
            continue
        parent = infer_parent(branch_id)
        missing[branch_id] = SourceAtom(
            id=branch_id,
            title=branch_title(branch_id),
            question="what",
            tags=list(BRANCH_TAGS),
            node_type="branch",
            parent_id=parent,
            answer=f"Nodo de organización de la base de conocimiento APOS: agrupa las ramas y átomos cuyo parent_id es `{branch_id}`.",
            provenance="Inferida por `tutor.kb_build` a partir de los `parent_id` de los átomos; no existe como archivo en `desk/atoms/`.",
            relative=Path("branches") / f"{branch_id}.md",
            synthesized=True,
        )
        if parent and parent not in known and parent not in missing:
            pending.append(parent)
    return sorted(missing.values(), key=lambda a: a.id)


def infer_parent(branch_id: str) -> str | None:
    """`branch-apos-core-structures` → `branch-apos`; `branch-apos` y `branch-sources-*` son raíces."""
    if branch_id == ROOT_BRANCH or branch_id.startswith("branch-sources-"):
        return None
    if branch_id.startswith(f"{ROOT_BRANCH}-"):
        return ROOT_BRANCH
    return None


def branch_title(branch_id: str) -> str:
    if branch_id in BRANCH_TITLES:
        return BRANCH_TITLES[branch_id]
    return branch_id.removeprefix("branch-").replace("-", " ").capitalize()


# -- planificar -------------------------------------------------------------------------


def plan(
    atoms: list[SourceAtom], atoms_dir: Path, pack_dir: Path | None, embedder_id: str
) -> BuildPlan:
    """Qué documentos tendrá la KB, con qué modelo y en qué ruta."""
    everything = [*atoms, *synthesize_branches(atoms)]
    by_id = {a.id for a in everything}
    namespaces = tag_namespaces(atoms_dir, everything)
    plan = BuildPlan(manifest=manifest(embedder_id), namespaces=namespaces)
    for atom in everything:
        if atom.parent_id and atom.parent_id not in by_id:
            raise ValueError(f"{atom.id}: parent_id {atom.parent_id!r} no existe")
        plan.docs.append(atom_doc(atom))
    plan.docs.append(relation_type_doc())
    models = {a.id: model_for(a) for a in everything}
    for atom in everything:
        if atom.parent_id:
            plan.docs.append(relation_doc(models[atom.id], atom.id, models[atom.parent_id], atom.parent_id))
    plan.docs.extend(category_doc(ns, spec) for ns, spec in sorted(namespaces.items()))
    plan.docs.append(agent_doc(pack_dir))
    plan.docs.append(projection_doc())
    return plan


def model_for(atom: SourceAtom) -> str:
    if atom.node_type == "branch":
        return "BranchNode"
    return "SourceAtom" if atom.relative.parts[0] == "sources" else "KnowledgeAtom"


def atom_doc(atom: SourceAtom) -> Doc:
    model = model_for(atom)
    if model == "BranchNode":
        path = f"taxonomy/{atom.id}.md"
        payload: dict[str, Any] = {
            "id": atom.id,
            "title": atom.title,
            "tags": atom.tags,
            "parent": atom.parent_id,
            "description": atom.answer,
            "provenance": atom.provenance,
        }
    else:
        folder = "sources" if model == "SourceAtom" else "knowledge"
        inner = Path(*atom.relative.parts[1:-1]) if len(atom.relative.parts) > 2 else Path()
        path = (Path(folder) / inner / f"{atom.id}.md").as_posix()
        payload = {
            "id": atom.id,
            "title": atom.title,
            "five_wh_one_plus": atom.question,
            "tags": atom.tags,
            "parent": atom.parent_id,
            "answer": atom.answer,
            "provenance": atom.provenance,
        }
    return Doc(model, path, payload)


def relation_type_doc() -> Doc:
    return Doc(
        "RelationTypeDoc",
        f"kgdb/relation_types/{RELATION}.md",
        {
            "title": RELATION,
            "name": RELATION,
            "direction": "directed",
            "cardinality": "many_to_one",
            "axis": "WHAT",
            "source_types": ["KnowledgeAtom", "BranchNode"],
            "target_types": ["BranchNode"],
            "condition": "",
            "description": "El origen es un hijo del destino en la taxonomía APOS: un átomo cuelga de una rama, "
            "una rama de otra rama. Proyección tipada del `parent_id` de los átomos fuente.",
        },
    )


def relation_doc(source_model: str, source: str, target_model: str, target: str) -> Doc:
    name = f"{RELATION}--{source}--{target}"
    return Doc(
        "RelationDoc",
        f"relations/{name}.md",
        {
            "title": f"{source} {RELATION} {target}",
            "source_id": f"{source_model}:{source}",
            "target_id": f"{target_model}:{target}",
            "relation_type": RELATION,
            "condition": "",
            "notes": "",
        },
    )


def tag_namespaces(atoms_dir: Path, atoms: list[SourceAtom]) -> dict[str, dict[str, Any]]:
    """Un namespace por cada prefijo de tag usado, descrito por `tag-namespaces.yaml` o por los extras."""
    declared: dict[str, dict[str, Any]] = {}
    source = atoms_dir / "tag-namespaces.yaml"
    if source.is_file():
        declared = dict((yaml.safe_load(source.read_text(encoding="utf-8")) or {}).get("namespaces") or {})
    used = {t.partition(":")[0] for a in atoms for t in a.tags} | {"agent"}
    namespaces: dict[str, dict[str, Any]] = {}
    for ns in sorted(used):
        spec = declared.get(ns) or EXTRA_NAMESPACES.get(ns)
        if spec is None:
            raise ValueError(f"namespace de tag sin descripción: {ns!r} (agrégalo a tag-namespaces.yaml)")
        namespaces[ns] = {
            "meaning": str(spec.get("meaning", "")),
            "use_when": str(spec.get("use_when", "")),
            "do_not_use_when": str(spec.get("do_not_use_when", "")),
            "examples": [str(e) for e in spec.get("examples") or []],
        }
    return namespaces


def category_doc(namespace: str, spec: dict[str, Any]) -> Doc:
    return Doc(
        "TagNamespaceDoc",
        f"categories/category-{namespace}.md",
        {
            "id": f"category-{namespace}",
            "title": namespace,
            "tag": namespace,
            "parent": None,
            "kind": "family",
            "examples": spec["examples"],
            "meaning": spec["meaning"],
            "use_when": spec["use_when"],
            "do_not_use_when": spec["do_not_use_when"],
        },
    )


def agent_doc(pack_dir: Path | None) -> Doc:
    persona = read_text(pack_dir, "persona.md", DEFAULT_PERSONA)
    policy = read_text(pack_dir, "prompt_policy.md", DEFAULT_POLICY)
    provenance = f"{pack_dir.as_posix()}/persona.md y prompt_policy.md" if pack_dir else None
    return Doc(
        "AgentDoc",
        f"agent/{AGENT_NAME}.md",
        {
            "id": AGENT_NAME,
            "title": "Tutor APOS",
            "role": ROLE,
            "projection": ROLE,
            "static": [{"tag": "type.knowledge.atom", "title": "Conocimiento APOS", "render": "cited"}],
            "dynamic": ["question", "history:6"],
            "tools": [],
            "on_failure": "closed",
            "policies": ["deny_if_no_context"],
            "tags": [f"agent:{ROLE}"],
            "provenance": provenance,
            "summary": "Tutor de la teoría APOS: explica estructuras, mecanismos y descomposición genética citando átomos.",
            "framing": persona,
            "instructions": policy,
        },
    )


def projection_doc() -> Doc:
    return Doc(
        "ProjectionDoc",
        f"projections/{PROJECTION_NAME}.md",
        {
            "name": ROLE,
            "stores": ["local"],
            "models": ["KnowledgeAtom", "BranchNode"],
            "relations": [{"name": RELATION, "mode": "read"}],
            "actions": [],
            "aliases": [],
            "naming": {},
            "display": {},
            "key": {},
            "matching": {"neighbors": 3, "threshold": 0.55},
            "exposed": False,
            "mutability": 0,
            "description": "Lo que ve el rol tutor: todos los átomos de conocimiento (KnowledgeAtom y "
            "SourceAtom) y la taxonomía (BranchNode) con sus aristas child_of, en solo lectura.",
        },
        name=PROJECTION_NAME,
    )


def manifest(embedder_id: str) -> dict[str, Any]:
    return {
        "kb": {
            "name": "apos",
            "kb_version": 1,
            "models": MODELS_PACKAGE,
            "pythonpath": "..",
            "categories": "required",
            "materialize": {"order": ["knowledge", "sources", "taxonomy"]},
            "index": {
                "models": ["KnowledgeAtom"],
                "text": "fields:answer",
                "text_id": "answer",
                "embedder_id": embedder_id,
            },
        }
    }


def read_text(directory: Path | None, name: str, default: str) -> str:
    """El texto del pack, con sus `## Títulos` demotidos a negrita: sldb no admite headings dentro de un campo."""
    if directory is None or not (directory / name).is_file():
        return default
    text = (directory / name).read_text(encoding="utf-8").strip()
    return re.sub(r"^#{1,6}\s+(.+?)\s*$", r"**\1**", text, flags=re.M)


# -- escribir ---------------------------------------------------------------------------


def write_kb(out: Path, plan: BuildPlan) -> None:
    """Limpia lo generado antes, escribe `kb.yaml` y `tag-namespaces.yaml`, arma el store y los `.md`."""
    from sldb.api import add_model, create_document, init_relations, init_store, rebuild_edges, update_store_indexes

    out = out.resolve()
    pythonpath = str((out / plan.manifest["kb"]["pythonpath"]).resolve())
    for name in GENERATED_DIRS:
        shutil.rmtree(out / name, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "kb.yaml").write_text(
        "# Lo que esta KB declara de sí misma (contrato kb_version 1, lo lee runtime/kb).\n"
        "# Generado por `python -m tutor.kb_build`; no editar a mano.\n"
        + yaml.safe_dump(plan.manifest, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (out / "tag-namespaces.yaml").write_text(
        "# Taxonomía de tags de esta KB: un namespace por categoría; el tag se escribe `ns:valor`.\n"
        "# Generado por `python -m tutor.kb_build` desde desk/atoms/tag-namespaces.yaml.\n"
        + yaml.safe_dump({"namespaces": plan.namespaces}, sort_keys=True, allow_unicode=True),
        encoding="utf-8",
    )
    store = init_store(out, force=True).store_path
    init_relations(store, pythonpath)
    for ref in MODEL_REFS:
        add_model(store, ref, pythonpath=pythonpath, actor=ACTOR)
    for doc in plan.docs:
        create_document(store, doc.model, out / doc.path, doc.payload, name=doc.doc_name, pythonpath=pythonpath, actor=ACTOR)
    update_store_indexes(store, pythonpath=pythonpath, wait=True)
    rebuild_edges(store, pythonpath, wait=True)


def validate(out: Path, embedder: Any | None) -> tuple[Any, Any]:
    """Abre con `kb` sin bloquear por errores; devuelve `(kb, report)`."""
    from kb import KnowledgeBase

    return KnowledgeBase.open_lenient(out.resolve(), embedder)


# -- CLI --------------------------------------------------------------------------------


def build(
    atoms_dir: Path, out: Path, *, pack_dir: Path | None = None, embedder_name: str | None = None, index: bool = True
) -> Any:
    """Todo el flujo: leer, planificar, escribir, validar, indexar. Devuelve el `ValidationReport`."""
    from tutor.embedding import get_embedder

    embedder = get_embedder(embedder_name)
    atoms = read_atoms(atoms_dir)
    built = plan(atoms, atoms_dir, pack_dir, embedder.id())
    log.info("%d átomos leídos, %d documentos a escribir", len(atoms), len(built.docs))
    write_kb(out, built)
    kb, report = validate(out, embedder)
    if report.is_valid and index:
        counts = kb.refresh_index()
        log.info("índice %s: %s", counts.index_path, counts.counts)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tutor.kb_build", description=__doc__.split("\n\n")[0])
    parser.add_argument("--atoms", type=Path, default=Path("desk/atoms"), help="Carpeta con los átomos fuente.")
    parser.add_argument("--out", type=Path, default=Path("kbs/apos"), help="Raíz de la KB a generar.")
    parser.add_argument(
        "--pack", type=Path, default=Path("apps/kb_agent/packs/apos"), help="Carpeta con persona.md y prompt_policy.md."
    )
    parser.add_argument("--embedder", default=None, help="hash (default, o TUTOR_EMBEDDER) | fastembed[:modelo].")
    parser.add_argument("--no-index", action="store_true", help="No refrescar el índice de embeddings.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")
    pack = args.pack if args.pack.is_dir() else None
    report = build(args.atoms, args.out, pack_dir=pack, embedder_name=args.embedder, index=not args.no_index)
    if not report.is_valid:
        for error in report.errors:
            print(error.line(), file=sys.stderr)
        print(f"KB inválida: {len(report.errors)} errores", file=sys.stderr)
        return 1
    print(f"KB válida en {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
