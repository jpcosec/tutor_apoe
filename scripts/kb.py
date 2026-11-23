#!/usr/bin/env python3
"""Visor local y CLI liviano para la base de conocimiento de Tutor APOE.

No es un chatbot y no requiere cuentas, claves ni conexión a un modelo de IA.
La búsqueda se resuelve con ``sldb find``; el visor solo muestra los átomos
encontrados y su contenido fuente.

Uso:
    python scripts/kb.py serve
    python scripts/kb.py search encapsulacion
    python scripts/kb.py check
"""
from __future__ import annotations

import argparse
import hashlib
import unicodedata
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / ".sldb"
ATOMS = ROOT / "desk" / "atoms"
WEB = ROOT / "web"
SUGGESTIONS = ROOT / "knowledge" / "didactic-suggestions"
EXPERT_MODULE = ROOT / "knowledge" / "expert-apoe"
EXPERTS = EXPERT_MODULE / "experts"
EXPERT_LOCK = Lock()
EXAMPLES_MODULE = ROOT / "knowledge" / "examples-apoe"
EXAMPLE_EXPERTS = EXAMPLES_MODULE / "experts"
EXAMPLE_LOCK = Lock()
LITERATURE_MODULE = ROOT / "knowledge" / "libro-e-investigaciones-apoe"
LITERATURE_LOCK = Lock()
# Prefer the CLI installed alongside this Python (e.g. the project venv).
SLDB = str(Path(sys.executable).with_name("sldb"))
if not Path(SLDB).is_file():
    SLDB = "sldb"


@dataclass(frozen=True)
class Atom:
    id: str
    title: str
    question: str
    tags: list[str]
    answer: str
    provenance: str
    node_type: str
    parent_id: str
    path: str


def _frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    _, meta, body = text.split("---\n", 2)
    return meta, body


def _field(meta: str, name: str) -> str:
    prefix = f"{name}:"
    for line in meta.splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip().strip('"')
    return ""


def _tags(meta: str) -> list[str]:
    lines = meta.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line == "tags:") + 1
    except StopIteration:
        return []
    tags: list[str] = []
    for line in lines[start:]:
        if not line.startswith((" ", "-")):
            break
        value = line.strip().removeprefix("-").strip()
        if value:
            tags.append(value)
    return tags


def _section(body: str, headings: tuple[str, ...]) -> str:
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if line.strip().lower() in {f"## {heading}".lower() for heading in headings}:
            result: list[str] = []
            for following in lines[index + 1:]:
                if following.startswith("## "):
                    break
                result.append(following)
            return "\n".join(result).strip()
    return ""


def read_atom(path: Path) -> Atom:
    meta, body = _frontmatter(path.read_text(encoding="utf-8"))
    return Atom(
        id=_field(meta, "id"),
        title=_field(meta, "title") or path.stem,
        question=_field(meta, "five_wh_one_plus"),
        tags=_tags(meta),
        answer=_section(body, ("Respuesta", "Answer")),
        provenance=_section(body, ("Procedencia", "Provenance")),
        node_type=_field(meta, "node_type") or "knowledge",
        parent_id=_field(meta, "parent_id"),
        path=str(path.relative_to(ROOT)),
    )


def atoms_by_id() -> dict[str, Atom]:
    return {
        atom.id: atom
        for path in ATOMS.rglob("atom-*.md")
        if (atom := read_atom(path)).id
    }


def sldb_find(term: str) -> list[str]:
    """Busca IDs con SLDB. El CLI es la autoridad del resultado."""
    command = [
        SLDB, "find", term, "--in", "both", "--type", "doc",
        "--store", str(STORE), "--pythonpath", str(ROOT), "--format", "json",
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if result.returncode:
        # Un store puede quedar incompleto tras actualizar SLDB. Conservamos la
        # consulta principal en SLDB, pero el visor no pierde acceso a sus
        # fuentes locales si falta un índice derivado.
        normal = _normalise(term)
        words = [word for word in normal.split() if len(word) >= 3]
        matches: list[tuple[int, str]] = []
        for atom in atoms_by_id().values():
            haystack = " ".join((atom.id, atom.title, atom.answer, " ".join(atom.tags)))
            searchable = _normalise(haystack)
            score = sum(1 for word in words if word in searchable)
            if score:
                matches.append((score, atom.id))
        if matches:
            matches.sort(key=lambda item: (-item[0], item[1]))
            return [atom_id for _, atom_id in matches]
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "SLDB no pudo buscar.")
    payload = json.loads(result.stdout)
    return list(dict.fromkeys(item["doc"] for item in payload.get("results", []) if item.get("doc")))


def atom_payload(atom: Atom) -> dict[str, object]:
    return {
        "id": atom.id,
        "title": atom.title,
        "question": atom.question,
        "tags": atom.tags,
        "answer": atom.answer,
        "provenance": atom.provenance,
        "node_type": atom.node_type,
        "parent_id": atom.parent_id,
        "path": atom.path,
    }


def _normalise(value: str) -> str:
    """Normaliza texto para una recuperación local transparente."""
    decomposed = unicodedata.normalize("NFD", value.lower())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()


QUERY_ALIASES = {
    "action": {"accion", "acciones", "actuar", "aplicar", "ejecutar"},
    "analysis": {"analisis", "calculo", "calculus", "limite", "limites"},
    "functions": {"funcion", "funciones"},
    "process": {"proceso", "procesos"},
    "interiorization": {"interiorizar", "interiorizacion", "interioriza"},
    "coordination": {"coordinar", "coordinacion", "coordina"},
    "reversal": {"reversion", "revertir", "revierte", "inversa", "inverso"},
    "de-encapsulation": {"desencapsular", "desencapsulacion", "desencapsula"},
    "encapsulation": {"encapsular", "encapsulacion", "encapsula"},
    "object": {"objeto", "objetos"},
    "schema": {"esquema", "esquemas"},
}
STOP_WORDS = {"a", "al", "con", "como", "de", "del", "el", "en", "es", "la", "las", "lo", "los", "me", "para", "por", "que", "quiero", "su", "un", "una", "y"}

CORE_ROUTE_IDS = {
    "process": (
        "atom-interiorization-translates-material-actions-into-processes",
        "atom-coordination-combines-processes-to-build-new-objects-or-processes",
        "atom-reversal-can-operate-after-de-encapsulation",
        "atom-de-encapsulation-recovers-the-underlying-process-of-an-object",
    ),
    "object": ("atom-encapsulation-treats-a-process-as-a-static-entity",),
    "schema": (
        "atom-schema-is-a-coherent-framework-of-linked-structures",
        "atom-schema-development-in-apos-uses-the-intra-inter-trans-triad",
    ),
}


def _query_topics(question: str) -> tuple[list[str], set[str]]:
    words = {word for word in _normalise(question).split() if word not in STOP_WORDS}
    topics = [topic for topic, aliases in QUERY_ALIASES.items() if words & aliases]
    return topics, words


def _rank_atoms(question: str, limit: int = 4) -> tuple[list[Atom], list[str]]:
    """Relaciona una pregunta con átomos por sus títulos, tags y respuestas.

    Esta capa no genera contenido: solo hace explícita una recuperación local
    sobre la misma base que presenta el visor.
    """
    topics, words = _query_topics(question)
    scored: list[tuple[int, Atom]] = []
    for atom in atoms_by_id().values():
        title = _normalise(atom.title)
        answer = _normalise(atom.answer)
        tags = " ".join(_normalise(tag) for tag in atom.tags)
        score = 0
        for topic in topics:
            if f"topic {topic}" in tags or topic in tags:
                score += 10
            if topic.rstrip("s") in title:
                score += 5
            if topic.rstrip("s") in answer:
                score += 2
        for word in words:
            if len(word) < 4:
                continue
            if word in title:
                score += 3
            if word in tags:
                score += 2
            if word in answer:
                score += 1
        if score:
            scored.append((score, atom))
    scored.sort(key=lambda item: (-item[0], item[1].title))
    return [atom for _, atom in scored[:limit]], topics


def _suggestion_path(domain: str, concept: str, examples: list[str]) -> Path:
    """Una propuesta igual se guarda una sola vez, aunque se consulte de nuevo."""
    safe_domain = re.sub(r"[^a-z0-9-]+", "-", _normalise(domain)).strip("-") or "sin-dominio"
    safe_concept = re.sub(r"[^a-z0-9-]+", "-", _normalise(concept)).strip("-") or "sin-concepto"
    digest = hashlib.sha256("\n".join(examples).encode("utf-8")).hexdigest()[:10]
    return SUGGESTIONS / safe_domain / f"{safe_concept}-{digest}.md"


def save_didactic_suggestion(
    *, domain: str, concept: str, request: str, examples: list[str], source_atoms: list[Atom]
) -> Path:
    """Registra una propuesta didáctica sin convertirla en átomo fuente."""
    path = _suggestion_path(domain, concept, examples)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    suggestion_id = f"didactic-{path.stem}"
    sources = "\n".join(f"  - {atom.id}" for atom in source_atoms)
    lines = [
        "---",
        f"id: {suggestion_id}",
        "status: proposed",
        f"domain: {domain}",
        f"concept: {concept}",
        "origin: internal-kb-template",
        "source_atoms:",
        sources,
        "---",
        "",
        f"# Sugerencias didácticas: {concept}",
        "",
        "## Solicitud que la generó",
        "",
        request,
        "",
        "## Ejemplos propuestos",
        "",
        *[f"- {example}" for example in examples],
        "",
        "## Nota de revisión",
        "",
        "Propuesta generada con una plantilla local. Revísala antes de usarla o promoverla a conocimiento fuente.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _didactic_examples(question: str, topics: list[str], atoms: list[Atom]) -> tuple[str, str, list[str], list[Atom]] | None:
    """Plantillas locales: solo generan ejemplos cuando la KB permite contextualizarlos."""
    words = set(_normalise(question).split())
    asks_examples = bool(words & {"ejemplo", "ejemplos", "listar", "lista", "sugerir", "sugerencias"})
    if not asks_examples or "action" not in topics:
        return None
    if not {"analysis", "functions"}.issubset(topics):
        return ("", "", [], [])
    source_id = "atom-function-genetic-decomposition-begins-with-actions-on-elements"
    by_id = atoms_by_id()
    source = by_id.get(source_id)
    if source is None:
        return None
    return (
        "análisis",
        "función real de una variable",
        [
            "Con una regla explícita, calcular f(3) si f(x) = 2x + 1.",
            "Dada una tabla, aplicar la regla para asignar a cada entrada un único valor de salida.",
            "Para una función dada, seguir una instrucción para determinar la salida correspondiente a una entrada.",
        ],
        [source],
    )


def consult(question: str) -> dict[str, object]:
    """Devuelve una consulta didáctica basada en átomos con procedencia."""
    clean_question = question.strip()
    if not clean_question:
        raise ValueError("Escribe una pregunta para consultar la base.")
    atoms, topics = _rank_atoms(clean_question)
    if not atoms:
        return {
            "question": clean_question,
            "answer": "No encontré un átomo que responda esa formulación. Prueba con términos como acción, proceso, función, esquema o reversión.",
            "examples": [],
            "atoms": [],
            "topics": topics,
        }

    didactic = _didactic_examples(clean_question, topics, atoms)
    if didactic is not None:
        domain, concept, examples, source_atoms = didactic
        if not examples:
            return {
                "question": clean_question,
                "answer": "Para proponer ejemplos de acciones necesito que indiques el dominio y el concepto matemático. Por ejemplo: “función real de una variable en análisis” o “ecuación lineal homogénea en álgebra lineal”.",
                "examples": [],
                "atoms": [],
                "topics": topics,
                "needs_instruction": True,
            }
        saved = save_didactic_suggestion(
            domain=domain,
            concept=concept,
            request=clean_question,
            examples=examples,
            source_atoms=source_atoms,
        )
        return {
            "question": clean_question,
            "answer": "Estos ejemplos se generaron desde el átomo de función vinculado. Quedaron registrados como propuesta didáctica pendiente de revisión.",
            "examples": examples,
            "atoms": [atom_payload(atom) for atom in source_atoms],
            "topics": topics,
            "suggestion_path": str(saved.relative_to(ROOT)) if saved.is_relative_to(ROOT) else saved.name,
        }

    normal_question = _normalise(clean_question)
    construction_words = {"obtener", "obtiene", "obtencion", "construir", "construye", "formar", "forma"}
    asks_for_construction = bool(set(normal_question.split()) & construction_words)
    route_atoms: list[Atom] = []
    route_answer = ""
    by_id = atoms_by_id()
    if "process" in topics and (asks_for_construction or len(set(topics) & {"interiorization", "coordination", "reversal", "de-encapsulation"}) > 0):
        route_atoms = [by_id[atom_id] for atom_id in CORE_ROUTE_IDS["process"] if atom_id in by_id]
        route_answer = (
            "La base registra cuatro rutas para construir un Proceso:\n"
            "• Acción → interiorización → Proceso.\n"
            "• Coordinación de procesos → nuevo Proceso (o nuevo Objeto).\n"
            "• Objeto → desencapsulación → Proceso; ese proceso puede revertirse para construir otro Proceso.\n"
            "• Proceso → reversión → nuevo Proceso, cuando se controla la transformación en sentido inverso."
        )
    elif "object" in topics and (asks_for_construction or "encapsulation" in topics):
        route_atoms = [by_id[atom_id] for atom_id in CORE_ROUTE_IDS["object"] if atom_id in by_id]
        route_answer = "La ruta que registra la base es: Proceso → encapsulación → Objeto. La encapsulación permite tratar el proceso como una totalidad o entidad sobre la que se pueden aplicar nuevas transformaciones."
    elif "schema" in topics:
        route_atoms = [by_id[atom_id] for atom_id in CORE_ROUTE_IDS["schema"] if atom_id in by_id]
        route_answer = (
            "Un Esquema organiza coherentemente acciones, procesos, objetos y otros esquemas mediante relaciones generales. "
            "Su desarrollo puede describirse con la tríada Intra–Inter–Trans: desde componentes aislados, pasando por sus relaciones, hasta una organización coherente capaz de justificar su alcance."
        )

    if route_atoms:
        seen = set()
        atoms = [atom for atom in route_atoms + atoms if not (atom.id in seen or seen.add(atom.id))][:4]
        return {
            "question": clean_question,
            "answer": route_answer,
            "examples": [],
            "atoms": [atom_payload(atom) for atom in atoms],
            "topics": topics,
        }

    answer = "\n\n".join(f"{atom.title}: {atom.answer}" for atom in atoms[:2])
    examples: list[str] = []
    return {
        "question": clean_question,
        "answer": answer,
        "examples": examples,
        "atoms": [atom_payload(atom) for atom in atoms],
        "topics": topics,
    }


def _replace_field(meta: str, name: str, value: str) -> str:
    line = f"{name}: {json.dumps(value, ensure_ascii=False)}"
    return re.sub(rf"^{re.escape(name)}:.*$", line, meta, flags=re.MULTILINE)


def _replace_tags(meta: str, tags: list[str]) -> str:
    block = "tags:\n" + "".join(f"  - {tag}\n" for tag in tags)
    pattern = r"^tags:\n(?:[ \t-].*\n)*"
    return re.sub(pattern, block, meta, flags=re.MULTILINE)


def _replace_section(body: str, title: str, value: str) -> str:
    replacement = f"## {title}\n\n{value.strip()}\n"
    pattern = rf"^## {re.escape(title)}\n.*?(?=^## |\Z)"
    updated, count = re.subn(pattern, replacement, body, count=1, flags=re.MULTILINE | re.DOTALL)
    return updated if count else body.rstrip() + "\n\n" + replacement


def update_atom(atom_id: str, data: dict[str, object]) -> Atom:
    """Actualiza campos editables de un átomo y refresca el índice SLDB."""
    atoms = atoms_by_id()
    atom = atoms.get(atom_id)
    if atom is None:
        raise KeyError("Átomo no encontrado.")
    title = data.get("title")
    question = data.get("question")
    answer = data.get("answer")
    provenance = data.get("provenance")
    node_type = data.get("node_type")
    parent_id = data.get("parent_id")
    tags = data.get("tags")
    if not all(isinstance(value, str) for value in (title, question, answer, provenance, node_type, parent_id)):
        raise ValueError("Título, pregunta, respuesta y procedencia deben ser texto.")
    if question not in {"what", "why", "how", "how_not", "when", "where", "for_whom"}:
        raise ValueError("La pregunta debe ser una de las opciones 5WH1+.")
    if not isinstance(tags, list) or not all(isinstance(tag, str) and re.fullmatch(r"[a-z][a-z0-9_]*:[a-z][a-z0-9_-]*", tag) for tag in tags):
        raise ValueError("Cada tag debe tener el formato namespace:valor.")
    path = ROOT / atom.path
    meta, body = _frontmatter(path.read_text(encoding="utf-8"))
    meta = _replace_field(meta, "title", title.strip())
    meta = _replace_field(meta, "five_wh_one_plus", question)
    meta = _replace_tags(meta, tags)
    meta = _replace_field(meta, "node_type", node_type.strip()) if "node_type:" in meta else meta.rstrip() + f"\nnode_type: {json.dumps(node_type.strip())}\n"
    meta = _replace_field(meta, "parent_id", parent_id.strip()) if "parent_id:" in meta else meta.rstrip() + f"\nparent_id: {json.dumps(parent_id.strip())}\n"
    body = _replace_section(body, "Respuesta", answer)
    body = _replace_section(body, "Procedencia", provenance)
    path.write_text(f"---\n{meta}---\n{body}", encoding="utf-8")
    refreshed = subprocess.run(
        [SLDB, "stores", "update", "--store", str(STORE), "--pythonpath", str(ROOT)],
        cwd=ROOT, text=True, capture_output=True,
    )
    if refreshed.returncode:
        raise RuntimeError("El átomo se guardó, pero SLDB no pudo reindexar: " + (refreshed.stderr.strip() or refreshed.stdout.strip()))
    return read_atom(path)


def create_child(parent_id: str, data: dict[str, object]) -> Atom:
    parent = atoms_by_id().get(parent_id)
    if parent is None:
        raise KeyError("Átomo padre no encontrado.")
    title = data.get("title")
    node_type = data.get("node_type", "knowledge")
    if not isinstance(title, str) or not title.strip() or not isinstance(node_type, str) or not node_type.strip():
        raise ValueError("El hijo necesita título y tipo de nodo.")
    normal = title.lower().translate(str.maketrans("áéíóúüñ", "aeiouun"))
    slug = re.sub(r"[^a-z0-9]+", "-", normal).strip("-")
    atom_id = f"atom-{slug}"
    if atom_id in atoms_by_id():
        raise ValueError("Ya existe un átomo con ese título.")
    path = ATOMS / "custom" / f"{atom_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join((
        "---", f"id: {atom_id}", f"title: {json.dumps(title.strip(), ensure_ascii=False)}",
        "five_wh_one_plus: what", "tags:", "  - system:apos", "  - topic:pending",
        "  - layer:theory", f"node_type: {json.dumps(node_type.strip())}",
        f"parent_id: {parent_id}", "---", "", f"# {title.strip()}", "",
        "## Respuesta", "", "Pendiente de redactar.", "", "## Procedencia", "",
        "Pendiente de documentar.", "",
    ))
    path.write_text(content, encoding="utf-8")
    refreshed = subprocess.run([SLDB, "stores", "update", "--store", str(STORE), "--pythonpath", str(ROOT)], cwd=ROOT, text=True, capture_output=True)
    if refreshed.returncode:
        raise RuntimeError("El hijo se creó, pero SLDB no pudo reindexar.")
    return read_atom(path)


DEFAULT_EXPERT_PROTOCOL = {
    "id": "apoe-expert-protocol",
    "title": "Protocolo de diálogo experto APOE",
    "instructions": "El protocolo aún no tiene preguntas. La coordinación debe configurarlas antes de invitar a especialistas.",
    "questions": [],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path, default: object) -> object:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


DEFAULT_LITERATURE_MODULE = {
    "id": "apoe-books-and-research",
    "title": "Libro APOE e investigaciones APOE",
    "description": "Catálogo trazable de libros, capítulos, artículos, tesis e investigaciones para orientar la curaduría de la base del Tutor APOE.",
    "collections": [
        {"id": "book", "title": "Libro APOE", "description": "Fuentes monográficas y capítulos de referencia."},
        {"id": "research", "title": "Investigaciones APOE", "description": "Artículos, tesis, informes y estudios empíricos."},
    ],
    "sources": [],
}


def literature_module() -> dict[str, object]:
    data = _read_json(LITERATURE_MODULE / "module.json", DEFAULT_LITERATURE_MODULE)
    if not isinstance(data, dict):
        return dict(DEFAULT_LITERATURE_MODULE)
    collections = data.get("collections")
    sources = data.get("sources")
    if not isinstance(collections, list) or not isinstance(sources, list):
        return dict(DEFAULT_LITERATURE_MODULE)
    return data


def add_literature_source(data: dict[str, object]) -> dict[str, object]:
    title = data.get("title")
    source_type = data.get("source_type")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Indica el título de la fuente.")
    if source_type not in {"book", "research"}:
        raise ValueError("El tipo debe ser libro o investigación.")
    def text(name: str) -> str:
        value = data.get(name, "")
        if not isinstance(value, str):
            raise ValueError(f"{name} debe ser texto.")
        return value.strip()
    year = text("year")
    if year and not re.fullmatch(r"[0-9]{4}", year):
        raise ValueError("El año debe tener cuatro dígitos.")
    source = {
        "id": f"source-{uuid4().hex[:10]}", "title": title.strip(), "source_type": source_type,
        "authors": text("authors"), "year": year, "topic": text("topic"),
        "citation": text("citation"), "location": text("location"), "notes": text("notes"),
        "created_at": _now(),
    }
    with LITERATURE_LOCK:
        module = literature_module()
        sources = module.get("sources")
        assert isinstance(sources, list)
        sources.append(source)
        module["sources"] = sources
        _write_json(LITERATURE_MODULE / "module.json", module)
    return source


def expert_protocol() -> dict[str, object]:
    data = _read_json(EXPERT_MODULE / "protocol.json", DEFAULT_EXPERT_PROTOCOL)
    return data if isinstance(data, dict) else dict(DEFAULT_EXPERT_PROTOCOL)


def _question_prompt(question: object) -> str:
    if isinstance(question, dict):
        prompt = question.get("prompt")
        return prompt if isinstance(prompt, str) else ""
    return question if isinstance(question, str) else ""


def _question_id(question: object, position: int) -> str:
    if isinstance(question, dict) and isinstance(question.get("id"), str):
        return question["id"]
    return f"P{position + 1:02d}"


def _question_followups(question: object) -> list[str]:
    if not isinstance(question, dict):
        return []
    followups = question.get("followups", [])
    return [item.strip() for item in followups if isinstance(item, str) and item.strip()] if isinstance(followups, list) else []


def set_expert_protocol(data: dict[str, object]) -> dict[str, object]:
    title = data.get("title")
    instructions = data.get("instructions")
    questions = data.get("questions")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("El protocolo necesita un título.")
    if not isinstance(instructions, str) or not instructions.strip():
        raise ValueError("El protocolo necesita instrucciones.")
    if not isinstance(questions, list) or not all(_question_prompt(question).strip() for question in questions):
        raise ValueError("El protocolo necesita una lista de preguntas no vacías.")
    previous = expert_protocol()
    protocol = {
        "id": "apoe-expert-protocol",
        "title": title.strip(),
        "instructions": instructions.strip(),
        "questions": questions,
        "updated_at": _now(),
    }
    for key in ("opening", "closing", "source", "record_schema"):
        if key in data:
            protocol[key] = data[key]
        elif key in previous:
            protocol[key] = previous[key]
    _write_json(EXPERT_MODULE / "protocol.json", protocol)
    return protocol


def _expert_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _normalise(name)).strip("-") or "especialista"
    return f"expert-{slug[:36]}-{uuid4().hex[:8]}"


def _expert_dir(expert_id: str) -> Path:
    if not re.fullmatch(r"expert-[a-z0-9-]+", expert_id):
        raise ValueError("Identificador de especialista inválido.")
    return EXPERTS / expert_id


def _rebuild_expert_module(persist: bool = True) -> dict[str, object]:
    experts: list[dict[str, object]] = []
    if EXPERTS.is_dir():
        for profile_path in sorted(EXPERTS.glob("*/profile.json")):
            profile = _read_json(profile_path, {})
            index = _read_json(profile_path.parent / "conversations" / "index.json", [])
            if not isinstance(profile, dict) or not isinstance(index, list):
                continue
            experts.append({
                "id": profile.get("id"),
                "name": profile.get("name"),
                "created_at": profile.get("created_at"),
                "conversations": len(index),
                "responses": sum(int(item.get("responses", 0)) for item in index if isinstance(item, dict)),
                "repository": str(profile_path.parent.relative_to(ROOT)),
            })
    module = {
        "title": "Módulo experto APOE",
        "updated_at": _now(),
        "protocol": expert_protocol().get("id"),
        "experts": experts,
        "note": "Las conversaciones permanecen en el repositorio propio de cada especialista; este índice las reúne sin sustituir los átomos fuente.",
    }
    if not persist:
        return module

    _write_json(EXPERT_MODULE / "module.json", module)
    lines = [
        "# Módulo experto APOE",
        "",
        "Este índice reúne repositorios de conversación de especialistas. Las entrevistas no modifican por sí solas los átomos fuente de la KB.",
        "",
        "El protocolo LAETEC v1.0 solicita conformidad y código de participante, recorre P01–P12 y genera un Markdown exportable al cierre para revisión humana antes de cualquier carga al Tutor APOE.",
        "",
        "## Especialistas",
        "",
    ]
    lines.extend(
        f"- {item['name']} — {item['conversations']} conversación(es), {item['responses']} respuesta(s) · `{item['repository']}`"
        for item in experts
    )
    if not experts:
        lines.append("- Aún no hay repositorios de especialistas.")
    lines.append("")
    (EXPERT_MODULE / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return module


def create_expert(name: str) -> dict[str, object]:
    clean_name = name.strip()
    if len(clean_name) < 3:
        raise ValueError("Indica el nombre de la persona experta.")
    expert_id = _expert_id(clean_name)
    directory = _expert_dir(expert_id)
    profile = {
        "id": expert_id,
        "name": clean_name,
        "created_at": _now(),
        "repository": str(directory.relative_to(ROOT)),
    }
    _write_json(directory / "profile.json", profile)
    _write_json(directory / "conversations" / "index.json", [])
    _rebuild_expert_module()
    return profile


def expert_data(expert_id: str) -> dict[str, object]:
    directory = _expert_dir(expert_id)
    profile = _read_json(directory / "profile.json", None)
    if not isinstance(profile, dict):
        raise KeyError("Especialista no encontrado.")
    conversations = _read_json(directory / "conversations" / "index.json", [])
    return {
        "expert": profile,
        "protocol": expert_protocol(),
        "conversations": conversations if isinstance(conversations, list) else [],
    }


def _transcript(directory: Path, conversation: dict[str, object], protocol: dict[str, object]) -> None:
    lines = [
        f"# Conversación {conversation['id']}",
        "",
        f"Protocolo: {protocol['title']}",
        f"Participante: {conversation.get('participant_code', 'sin-código')}",
        f"Conformidad: {conversation.get('consent', 'sin información')}",
        f"Estado: {conversation.get('status', 'sin información')}",
        "",
        "## Respuestas",
        "",
    ]
    for response in conversation.get("responses", []):
        lines.extend((f"### {response['question_id']} · {response['question']}", "", response["answer"], "", f"Cobertura: {response.get('coverage', 'sin información')}", ""))
    if not conversation.get("responses"):
        lines.append("Aún no hay respuestas.")
    (directory / "conversations" / f"{conversation['id']}.md").write_text("\n".join(lines), encoding="utf-8")


def _save_conversation_summary(directory: Path, conversation: dict[str, object]) -> None:
    summaries = _read_json(directory / "conversations" / "index.json", [])
    if isinstance(summaries, list):
        for item in summaries:
            if isinstance(item, dict) and item.get("id") == conversation["id"]:
                item.update({"responses": len(conversation.get("responses", [])), "status": conversation.get("status"), "completed": conversation.get("completed"), "updated_at": conversation.get("updated_at")})
        _write_json(directory / "conversations" / "index.json", summaries)


def export_expert_conversation(expert_id: str, conversation_id: str) -> Path:
    directory = _expert_dir(expert_id)
    conversation = _read_json(directory / "conversations" / f"{conversation_id}.json", None)
    profile = _read_json(directory / "profile.json", None)
    if not isinstance(conversation, dict) or not isinstance(profile, dict):
        raise KeyError("Conversación o especialista no encontrado.")
    protocol = expert_protocol()
    lines = [
        "---",
        f"title: Entrevista APOE {conversation_id}",
        f"participant_code: {conversation.get('participant_code', 'sin-código')}",
        f"consent: {conversation.get('consent', 'sin información')}",
        f"status: {conversation.get('status', 'sin información')}",
        f"protocol: {protocol.get('id', 'sin información')}",
        "---",
        "",
        "# Registro exportable de entrevista APOE",
        "",
        f"Especialista: {profile.get('name', 'sin información')}",
        "",
        "Este archivo es una fuente de entrevista para revisión humana. No incorpora átomos al Tutor APOE automáticamente.",
        "",
    ]
    for turn in conversation.get("turns", []):
        if not isinstance(turn, dict):
            continue
        lines.extend((f"## {turn.get('question_id', 'sin id')} · turno {turn.get('turn', '?')}", "", f"Pregunta: {turn.get('question', '')}", "", f"Respuesta: {turn.get('answer', '')}", "", f"Cobertura: {turn.get('coverage', 'sin información')}", ""))
    validation = conversation.get("synthesis_validation")
    if isinstance(validation, dict):
        lines.extend(("## Validación de síntesis", "", f"Validada: {validation.get('validated', False)}", "", f"Correcciones: {validation.get('corrections', 'sin información')}", ""))
    path = directory / "exports" / f"{conversation_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def pause_expert_conversation(expert_id: str, conversation_id: str) -> dict[str, object]:
    directory = _expert_dir(expert_id)
    path = directory / "conversations" / f"{conversation_id}.json"
    conversation = _read_json(path, None)
    if not isinstance(conversation, dict):
        raise KeyError("Conversación no encontrada.")
    if conversation.get("status") != "active":
        raise ValueError("Solo se puede pausar una conversación activa.")
    conversation["status"] = "paused"
    conversation["paused_at"] = _now()
    conversation["updated_at"] = conversation["paused_at"]
    _write_json(path, conversation)
    _save_conversation_summary(directory, conversation)
    _transcript(directory, conversation, expert_protocol())
    _rebuild_expert_module()
    return {"conversation": conversation, "next_question": _active_question(expert_protocol(), conversation)}


def resume_expert_conversation(expert_id: str, conversation_id: str) -> dict[str, object]:
    directory = _expert_dir(expert_id)
    path = directory / "conversations" / f"{conversation_id}.json"
    conversation = _read_json(path, None)
    if not isinstance(conversation, dict):
        raise KeyError("Conversación no encontrada.")
    if conversation.get("status") != "paused":
        raise ValueError("Solo se puede reanudar una conversación pausada.")
    conversation["status"] = "active"
    conversation["updated_at"] = _now()
    _write_json(path, conversation)
    _save_conversation_summary(directory, conversation)
    _transcript(directory, conversation, expert_protocol())
    _rebuild_expert_module()
    return {"conversation": conversation, "next_question": _active_question(expert_protocol(), conversation)}


def validate_expert_conversation(expert_id: str, conversation_id: str, validated: bool, corrections: str = "", ended_early: bool = False) -> dict[str, object]:
    directory = _expert_dir(expert_id)
    path = directory / "conversations" / f"{conversation_id}.json"
    conversation = _read_json(path, None)
    if not isinstance(conversation, dict):
        raise KeyError("Conversación no encontrada.")
    if conversation.get("status") not in {"awaiting_validation", "active", "paused"}:
        raise ValueError("La conversación ya está cerrada.")
    conversation["status"] = "closed_early" if ended_early else "validated" if validated else "closed_unvalidated"
    conversation["completed"] = True
    conversation["synthesis_validation"] = {"validated": validated, "corrections": corrections.strip() or "sin información", "ended_early": ended_early, "at": _now()}
    conversation["updated_at"] = _now()
    _write_json(path, conversation)
    _save_conversation_summary(directory, conversation)
    _transcript(directory, conversation, expert_protocol())
    export_path = export_expert_conversation(expert_id, conversation_id)
    _rebuild_expert_module()
    return {"conversation": conversation, "synthesis": conversation.get("responses", []), "export_path": str(export_path.relative_to(ROOT))}


def _active_question(protocol: dict[str, object], conversation: dict[str, object]) -> dict[str, object] | None:
    questions = protocol.get("questions", [])
    question_index = conversation.get("question_index")
    if not isinstance(questions, list) or not isinstance(question_index, int) or question_index >= len(questions):
        return None
    question = questions[question_index]
    question_id = _question_id(question, question_index)
    followups_used = conversation.get("followups_used", 0)
    followups = _question_followups(question)
    if isinstance(followups_used, int) and followups_used > 0 and followups_used <= len(followups):
        return {"id": question_id, "prompt": followups[followups_used - 1], "kind": "followup", "position": question_index + 1}
    prompt = _question_prompt(question)
    previous_turns = [turn for turn in conversation.get("turns", []) if isinstance(turn, dict) and question_id in turn.get("related_questions", [])]
    if previous_turns:
        sources = ", ".join(f"turno {turn.get('turn', '?')}" for turn in previous_turns)
        prompt = f"Parte aún por explorar de {question_id}. El tema fue adelantado en {sources}; complete o matice solo lo que falte.\n\n{prompt}"
    return {"id": question_id, "prompt": prompt, "kind": "main", "position": question_index + 1, "prior_turns": [turn.get("turn") for turn in previous_turns]}


def start_expert_conversation(expert_id: str, participant_code: str, consent: bool) -> dict[str, object]:
    data = expert_data(expert_id)
    protocol = data["protocol"]
    questions = protocol.get("questions", [])
    if not isinstance(questions, list) or not questions:
        raise ValueError("La coordinación todavía no ha configurado las preguntas del protocolo.")
    clean_code = participant_code.strip()
    if consent and not clean_code:
        raise ValueError("Indica tu código de participante antes de comenzar.")
    expert = data["expert"]
    directory = _expert_dir(expert_id)
    conversation = {
        "id": f"conversation-{uuid4().hex[:10]}",
        "expert_id": expert_id,
        "created_at": _now(),
        "updated_at": _now(),
        "participant_code": clean_code or "sin-código",
        "consent": "accepted" if consent else "declined",
        "status": "active" if consent else "declined",
        "question_index": 0,
        "followups_used": 0,
        "coverage": {},
        "turns": [],
        "responses": [],
        "completed": not consent,
    }
    _write_json(directory / "conversations" / f"{conversation['id']}.json", conversation)
    index = data["conversations"]
    index.append({"id": conversation["id"], "created_at": conversation["created_at"], "participant_code": conversation["participant_code"], "consent": conversation["consent"], "responses": 0, "status": conversation["status"], "completed": conversation["completed"]})
    _write_json(directory / "conversations" / "index.json", index)
    _transcript(directory, conversation, protocol)
    _rebuild_expert_module()
    return {"conversation": conversation, "question": _active_question(protocol, conversation), "expert": expert, "protocol": protocol}


def record_expert_response(expert_id: str, conversation_id: str, answer: str, coverage: str = "complete", related_questions: list[str] | None = None) -> dict[str, object]:
    clean_answer = answer.strip()
    if not clean_answer:
        raise ValueError("Escribe una respuesta antes de continuar.")
    directory = _expert_dir(expert_id)
    path = directory / "conversations" / f"{conversation_id}.json"
    conversation = _read_json(path, None)
    if not isinstance(conversation, dict):
        raise KeyError("Conversación no encontrada.")
    protocol = expert_protocol()
    questions = protocol.get("questions", [])
    index = conversation.get("question_index")
    if not isinstance(questions, list) or not isinstance(index, int) or index >= len(questions) or conversation.get("completed") or conversation.get("status") != "active":
        raise ValueError("La conversación ya no tiene preguntas pendientes.")
    if coverage not in {"complete", "partial", "omitted"}:
        raise ValueError("La cobertura debe ser completa, parcial u omitida.")
    active = _active_question(protocol, conversation)
    if active is None:
        raise ValueError("No se encontró la pregunta activa.")
    turn = {"turn": len(conversation.get("turns", [])) + 1, "question_id": active["id"], "question_kind": active["kind"], "question": active["prompt"], "answer": clean_answer, "coverage": coverage, "related_questions": related_questions or [], "answered_at": _now()}
    conversation.setdefault("responses", []).append(turn)
    conversation.setdefault("turns", []).append(turn)
    conversation.setdefault("coverage", {})[active["id"]] = coverage
    question = questions[index]
    followups = _question_followups(question)
    followups_used = conversation.get("followups_used", 0)
    if coverage == "partial" and isinstance(followups_used, int) and followups_used < min(2, len(followups)):
        conversation["followups_used"] = followups_used + 1
    else:
        conversation["question_index"] = index + 1
        conversation["followups_used"] = 0
    conversation["updated_at"] = _now()
    conversation["completed"] = conversation["question_index"] >= len(questions)
    if conversation["completed"]:
        conversation["status"] = "awaiting_validation"
    _write_json(path, conversation)
    _transcript(directory, conversation, protocol)
    _save_conversation_summary(directory, conversation)
    _rebuild_expert_module()
    next_question = None if conversation["completed"] else _active_question(protocol, conversation)
    return {"conversation": conversation, "next_question": next_question}


def examples_protocol() -> dict[str, object]:
    data = _read_json(EXAMPLES_MODULE / "protocol.json", {})
    return data if isinstance(data, dict) else {}


def _example_dir(expert_id: str) -> Path:
    if not re.fullmatch(r"example-[a-z0-9-]+", expert_id):
        raise ValueError("Identificador de especialista inválido.")
    return EXAMPLE_EXPERTS / expert_id


def create_example_expert(name: str) -> dict[str, object]:
    clean_name = name.strip()
    if len(clean_name) < 3:
        raise ValueError("Indica el nombre de la persona experta.")
    expert_id = "example-" + _expert_id(clean_name).removeprefix("expert-")
    directory = _example_dir(expert_id)
    profile = {"id": expert_id, "name": clean_name, "created_at": _now(), "repository": str(directory.relative_to(ROOT))}
    _write_json(directory / "profile.json", profile)
    _write_json(directory / "conversations" / "index.json", [])
    return profile


def example_data(expert_id: str) -> dict[str, object]:
    directory = _example_dir(expert_id)
    profile = _read_json(directory / "profile.json", None)
    if not isinstance(profile, dict):
        raise KeyError("Especialista no encontrado.")
    conversations = _read_json(directory / "conversations" / "index.json", [])
    return {"expert": profile, "protocol": examples_protocol(), "conversations": conversations if isinstance(conversations, list) else []}


def _example_questions(protocol: dict[str, object], selected_domains: list[str], concepts: dict[str, str]) -> list[dict[str, object]]:
    domains = protocol.get("domains", [])
    depth = protocol.get("deepening", [])
    result: list[dict[str, object]] = []
    for domain in domains if isinstance(domains, list) else []:
        if not isinstance(domain, dict) or domain.get("id") not in selected_domains:
            continue
        domain_id = domain["id"]
        concept = concepts.get(domain_id, "").strip() or str(domain.get("concept", ""))
        for suffix, field in (("A", "action"), ("I", "interiorization")):
            result.append({"id": f"{domain_id}-{suffix}", "domain": domain_id, "concept": concept, "label": "Acción" if suffix == "A" else "Interiorización", "prompt": domain.get(field, "")})
        for item in depth if isinstance(depth, list) else []:
            if isinstance(item, dict):
                result.append({"id": f"{domain_id}-{item.get('id')}", "domain": domain_id, "concept": concept, "label": item.get("label", "Profundización"), "prompt": item.get("prompt", "")})
    return result


def _example_current(conversation: dict[str, object]) -> dict[str, object] | None:
    questions = conversation.get("questions", [])
    position = conversation.get("position", 0)
    return questions[position] if isinstance(questions, list) and isinstance(position, int) and position < len(questions) and isinstance(questions[position], dict) else None


def start_example_conversation(expert_id: str, participant_code: str, consent: bool, domains: list[str], concepts: dict[str, str]) -> dict[str, object]:
    data = example_data(expert_id)
    clean_code = participant_code.strip()
    if consent and not clean_code:
        raise ValueError("Indica tu código de participante antes de comenzar.")
    questions = _example_questions(data["protocol"], domains, concepts)
    if consent and not questions:
        raise ValueError("Selecciona al menos un dominio.")
    directory = _example_dir(expert_id)
    conversation = {"id": f"example-conversation-{uuid4().hex[:10]}", "expert_id": expert_id, "participant_code": clean_code or "sin-código", "consent": "accepted" if consent else "declined", "status": "active" if consent else "declined", "created_at": _now(), "updated_at": _now(), "questions": questions, "position": 0, "turns": [], "completed": not consent}
    _write_json(directory / "conversations" / f"{conversation['id']}.json", conversation)
    index = data["conversations"]
    index.append({"id": conversation["id"], "participant_code": conversation["participant_code"], "status": conversation["status"], "responses": 0, "created_at": conversation["created_at"]})
    _write_json(directory / "conversations" / "index.json", index)
    return {"conversation": conversation, "question": _example_current(conversation)}


def record_example_response(expert_id: str, conversation_id: str, answer: str, coverage: str, origin: str) -> dict[str, object]:
    directory = _example_dir(expert_id)
    path = directory / "conversations" / f"{conversation_id}.json"
    conversation = _read_json(path, None)
    if not isinstance(conversation, dict) or conversation.get("status") != "active":
        raise ValueError("La conversación no está activa.")
    question = _example_current(conversation)
    if question is None:
        raise ValueError("No hay una pregunta pendiente.")
    if coverage not in {"complete", "partial", "omitted", "not_proposed", "pending"}:
        raise ValueError("Cobertura inválida.")
    turn = {"turn": len(conversation["turns"]) + 1, "question_id": question["id"], "domain": question["domain"], "concept": question["concept"], "label": question["label"], "prompt": question["prompt"], "answer": answer.strip() or "sin información", "coverage": coverage, "origin": origin if origin in {"expert", "interviewer_stimulus", "mixed"} else "expert", "answered_at": _now()}
    conversation["turns"].append(turn)
    followup_count = question.get("followup_count", 0)
    if coverage == "partial" and isinstance(followup_count, int) and followup_count < 2:
        prompts = [
            "¿Qué diría o escribiría exactamente el estudiante y de qué indicación, fórmula o representación depende su actividad?",
            "¿Qué cambio haría a la tarea para distinguir esta construcción de una ejecución más fluida de la acción?",
        ]
        followup = dict(question)
        followup["id"] = f"{question['id']}-R{followup_count + 1}"
        followup["label"] = f"{question['label']} · repregunta {followup_count + 1}"
        followup["prompt"] = prompts[followup_count]
        followup["followup_count"] = followup_count + 1
        conversation["questions"].insert(conversation["position"] + 1, followup)
    conversation["position"] += 1
    conversation["updated_at"] = _now()
    conversation["completed"] = conversation["position"] >= len(conversation["questions"])
    if conversation["completed"]:
        conversation["status"] = "awaiting_validation"
    _write_json(path, conversation)
    return {"conversation": conversation, "next_question": _example_current(conversation)}


def set_example_pause(expert_id: str, conversation_id: str, paused: bool) -> dict[str, object]:
    directory = _example_dir(expert_id)
    path = directory / "conversations" / f"{conversation_id}.json"
    conversation = _read_json(path, None)
    if not isinstance(conversation, dict):
        raise KeyError("Conversación no encontrada.")
    expected, target = ("active", "paused") if paused else ("paused", "active")
    if conversation.get("status") != expected:
        raise ValueError("La conversación no está en un estado que permita esta operación.")
    conversation["status"] = target
    conversation["updated_at"] = _now()
    _write_json(path, conversation)
    return {"conversation": conversation, "next_question": _example_current(conversation)}


def export_example_conversation(expert_id: str, conversation_id: str) -> Path:
    directory = _example_dir(expert_id)
    conversation = _read_json(directory / "conversations" / f"{conversation_id}.json", None)
    if not isinstance(conversation, dict):
        raise KeyError("Conversación no encontrada.")
    lines = ["---", f"title: Ejemplos APOE y DG {conversation_id}", f"participant_code: {conversation.get('participant_code')}", f"consent: {conversation.get('consent')}", f"status: {conversation.get('status')}", "---", "", "# Banco de casos APOE y fragmentos de DG", ""]
    for turn in conversation.get("turns", []):
        if isinstance(turn, dict):
            lines.extend((f"## {turn['question_id']} · {turn['concept']}", "", f"Pregunta: {turn['prompt']}", "", f"Respuesta: {turn['answer']}", "", f"Estado: {turn['coverage']} · Procedencia: {turn['origin']}", ""))
    path = directory / "exports" / f"{conversation_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def close_example_conversation(expert_id: str, conversation_id: str, validated: bool, corrections: str = "") -> dict[str, object]:
    directory = _example_dir(expert_id)
    path = directory / "conversations" / f"{conversation_id}.json"
    conversation = _read_json(path, None)
    if not isinstance(conversation, dict):
        raise KeyError("Conversación no encontrada.")
    if conversation.get("status") not in {"active", "awaiting_validation"}:
        raise ValueError("La conversación ya está cerrada.")
    conversation["status"] = "validated" if validated else "closed_unvalidated"
    conversation["completed"] = True
    conversation["validation"] = {"validated": validated, "corrections": corrections.strip() or "sin información", "at": _now()}
    conversation["updated_at"] = _now()
    _write_json(path, conversation)
    export_path = export_example_conversation(expert_id, conversation_id)
    return {"conversation": conversation, "export_path": str(export_path.relative_to(ROOT))}
PAGE = """<!doctype html>
<html lang=\"es\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Tutor APOE · Base de conocimiento</title>
<style>
body{font:16px system-ui,sans-serif;max-width:980px;margin:0 auto;padding:2rem;color:#18212b;background:#fafafa} h1{margin-bottom:.25rem} .muted{color:#586675} form{display:flex;gap:.5rem;margin:1.5rem 0} input{flex:1;padding:.7rem;font:inherit;border:1px solid #9ba8b4;border-radius:.4rem}button{padding:.7rem 1rem;font:inherit;background:#155e75;color:white;border:0;border-radius:.4rem;cursor:pointer}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:.75rem}.card{background:white;border:1px solid #d7dee5;border-radius:.5rem;padding:1rem;cursor:pointer}.card:hover{border-color:#155e75}.tag{display:inline-block;background:#e6f4f1;color:#135c56;border-radius:1rem;padding:.12rem .45rem;font-size:.8rem;margin:.15rem .2rem 0 0}#detail{white-space:pre-wrap;background:white;border:1px solid #d7dee5;border-radius:.5rem;padding:1rem;min-height:6rem;margin-top:1rem}a{color:#155e75}code{background:#edf1f4;padding:.1rem .25rem}
</style>
<h1>Tutor APOE</h1><p class=\"muted\">Explora la base de conocimiento APOS. La búsqueda usa SLDB; no hay chatbot ni IA generativa.</p>
<form id=\"search\"><input id=\"term\" autofocus placeholder=\"Ej.: encapsulación o topic:schema\"><button>Buscar</button></form>
<p id=\"status\" class=\"muted\"></p><div id=\"results\" class=\"grid\"></div><article id=\"detail\">Elige un átomo para leerlo completo.</article>
<p class=\"muted\">En terminal: <code>python scripts/kb.py search topic:encapsulation</code> · <code>python scripts/kb.py check</code></p>
<script>
const results=document.querySelector('#results'), detail=document.querySelector('#detail'), status=document.querySelector('#status');
function show(a){detail.textContent=`${a.title}\n\n${a.answer || 'Sin respuesta.'}${a.provenance ? '\n\nProcedencia\n'+a.provenance : ''}\n\nArchivo: ${a.path}`}
async function search(q=''){status.textContent='Buscando…'; const r=await fetch('/api/search?q='+encodeURIComponent(q)); const d=await r.json(); if(!r.ok){status.textContent=d.detail;return} status.textContent=`${d.atoms.length} átomo(s) encontrado(s)`; results.replaceChildren(...d.atoms.map(a=>{const e=document.createElement('button');e.className='card';e.innerHTML=`<strong>${a.title}</strong><br><small>${a.question||''}</small><p>${a.tags.map(t=>`<span class=tag>${t}</span>`).join('')}</p>`;e.onclick=()=>show(a);return e})); if(d.atoms.length)show(d.atoms[0])}
document.querySelector('#search').onsubmit=e=>{e.preventDefault();search(document.querySelector('#term').value)}; search();
</script></html>"""


class Handler(BaseHTTPRequestHandler):
    def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _payload(self, limit: int = 200_000) -> dict[str, object]:
        size = int(self.headers.get("Content-Length", "0"))
        if size > limit:
            raise ValueError("El envío es demasiado grande.")
        payload = json.loads(self.rfile.read(size))
        if not isinstance(payload, dict):
            raise ValueError("El cuerpo debe ser un objeto.")
        return payload

    def _file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _download(self, path: Path) -> None:
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 - API de BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._file(WEB / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/expert" or parsed.path.startswith("/expert/"):
            self._file(WEB / "expert.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/examples" or parsed.path.startswith("/examples/"):
            self._file(WEB / "examples.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/bibliografia":
            self._file(WEB / "literature.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/visualizations/matrix-vector":
            self._file(WEB / "matrix_vector_geogebra.html", "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/web/"):
            filename = parsed.path.removeprefix("/web/")
            content_types = {"theme.css": "text/css; charset=utf-8", "hierarchy.js": "text/javascript; charset=utf-8", "mindmap.js": "text/javascript; charset=utf-8", "mindmap.css": "text/css; charset=utf-8", "expert.js": "text/javascript; charset=utf-8", "expert.css": "text/css; charset=utf-8", "examples.js": "text/javascript; charset=utf-8", "examples.css": "text/css; charset=utf-8", "literature.js": "text/javascript; charset=utf-8", "literature.css": "text/css; charset=utf-8", "matrix_vector_geogebra.js": "text/javascript; charset=utf-8", "matrix_vector_geogebra.css": "text/css; charset=utf-8"}
            if filename in content_types:
                self._file(WEB / filename, content_types[filename])
                return
        if parsed.path == "/api/expert-protocol":
            self._json(expert_protocol())
            return
        if parsed.path == "/api/examples-protocol":
            self._json(examples_protocol())
            return
        if parsed.path == "/api/literature":
            with LITERATURE_LOCK:
                self._json(literature_module())
            return
        if parsed.path.startswith("/api/examples/") and parsed.path.endswith("/export"):
            expert_id = unquote(parsed.path.removeprefix("/api/examples/").removesuffix("/export").rstrip("/"))
            conversation_id = parse_qs(parsed.query).get("conversation", [""])[0]
            try:
                self._download(export_example_conversation(expert_id, conversation_id))
            except (KeyError, ValueError) as error:
                self._json({"detail": str(error)}, HTTPStatus.NOT_FOUND)
            return
        if parsed.path.startswith("/api/examples/"):
            expert_id = unquote(parsed.path.removeprefix("/api/examples/").strip("/"))
            try:
                self._json(example_data(expert_id))
            except (KeyError, ValueError) as error:
                self._json({"detail": str(error)}, HTTPStatus.NOT_FOUND)
            return
        if parsed.path == "/api/expert-module":
            with EXPERT_LOCK:
                self._json(_rebuild_expert_module(persist=False))
            return
        if parsed.path.startswith("/api/experts/") and parsed.path.endswith("/export"):
            expert_id = unquote(parsed.path.removeprefix("/api/experts/").removesuffix("/export").rstrip("/"))
            conversation_id = parse_qs(parsed.query).get("conversation", [""])[0]
            try:
                export_path = export_expert_conversation(expert_id, conversation_id)
                self._download(export_path)
            except (KeyError, ValueError) as error:
                self._json({"detail": str(error)}, HTTPStatus.NOT_FOUND)
            return
        if parsed.path.startswith("/api/experts/"):
            expert_id = unquote(parsed.path.removeprefix("/api/experts/").strip("/"))
            try:
                self._json(expert_data(expert_id))
            except (KeyError, ValueError) as error:
                self._json({"detail": str(error)}, HTTPStatus.NOT_FOUND)
            return
        if parsed.path == "/api/search":
            term = parse_qs(parsed.query).get("q", [""])[0].strip()
            docs = atoms_by_id()
            try:
                ids = sldb_find(term) if term else sorted(docs)
            except RuntimeError as error:
                self._json({"detail": str(error)}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            self._json({"atoms": [atom_payload(docs[doc]) for doc in ids if doc in docs]})
            return
        if parsed.path.startswith("/api/atoms/"):
            atom = atoms_by_id().get(unquote(parsed.path.rsplit("/", 1)[-1]))
            if atom is None:
                self._json({"detail": "Átomo no encontrado."}, HTTPStatus.NOT_FOUND)
            else:
                self._json(atom_payload(atom))
            return
        self._json({"detail": "Ruta no encontrada."}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - API de BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        if parsed.path == "/api/literature":
            try:
                self._json({"source": add_literature_source(self._payload(30_000))}, HTTPStatus.CREATED)
            except (ValueError, json.JSONDecodeError) as error:
                self._json({"detail": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/examples":
            try:
                payload = self._payload(10_000)
                name = payload.get("name")
                if not isinstance(name, str):
                    raise ValueError("El nombre debe ser texto.")
                with EXAMPLE_LOCK:
                    expert = create_example_expert(name)
                host = self.headers.get("Host", "127.0.0.1:8000")
                self._json({"expert": expert, "link": f"http://{host}/examples/{expert['id']}"}, HTTPStatus.CREATED)
            except (ValueError, json.JSONDecodeError) as error:
                self._json({"detail": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path.startswith("/api/examples/") and parsed.path.endswith("/start"):
            expert_id = unquote(parsed.path.removeprefix("/api/examples/").removesuffix("/start").rstrip("/"))
            try:
                payload = self._payload(20_000)
                code, consent, domains, concepts = payload.get("participant_code", ""), payload.get("consent"), payload.get("domains", []), payload.get("concepts", {})
                if not isinstance(code, str) or not isinstance(consent, bool) or not isinstance(domains, list) or not all(isinstance(item, str) for item in domains) or not isinstance(concepts, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in concepts.items()):
                    raise ValueError("Los datos iniciales no son válidos.")
                with EXAMPLE_LOCK:
                    self._json(start_example_conversation(expert_id, code, consent, domains, concepts), HTTPStatus.CREATED)
            except KeyError as error:
                self._json({"detail": str(error)}, HTTPStatus.NOT_FOUND)
            except (ValueError, json.JSONDecodeError) as error:
                self._json({"detail": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path.startswith("/api/examples/") and parsed.path.endswith("/responses"):
            expert_id, _, _ = unquote(parsed.path.removeprefix("/api/examples/")).partition("/")
            try:
                payload = self._payload(100_000)
                conversation_id, answer, coverage, origin = payload.get("conversation_id"), payload.get("answer"), payload.get("coverage", "complete"), payload.get("origin", "expert")
                if not all(isinstance(value, str) for value in (conversation_id, answer, coverage, origin)):
                    raise ValueError("La respuesta no es válida.")
                with EXAMPLE_LOCK:
                    self._json(record_example_response(expert_id, conversation_id, answer, coverage, origin))
            except (ValueError, json.JSONDecodeError) as error:
                self._json({"detail": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path.startswith("/api/examples/") and parsed.path.endswith("/close"):
            expert_id = unquote(parsed.path.removeprefix("/api/examples/").removesuffix("/close").rstrip("/"))
            try:
                payload = self._payload(20_000)
                conversation_id, validated, corrections = payload.get("conversation_id"), payload.get("validated"), payload.get("corrections", "")
                if not isinstance(conversation_id, str) or not isinstance(validated, bool) or not isinstance(corrections, str):
                    raise ValueError("El cierre no es válido.")
                with EXAMPLE_LOCK:
                    self._json(close_example_conversation(expert_id, conversation_id, validated, corrections))
            except (KeyError, ValueError, json.JSONDecodeError) as error:
                self._json({"detail": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path.startswith("/api/examples/") and (parsed.path.endswith("/pause") or parsed.path.endswith("/resume")):
            suffix = "pause" if parsed.path.endswith("/pause") else "resume"
            expert_id = unquote(parsed.path.removeprefix("/api/examples/").removesuffix("/" + suffix).rstrip("/"))
            try:
                payload = self._payload(10_000)
                conversation_id = payload.get("conversation_id")
                if not isinstance(conversation_id, str):
                    raise ValueError("Indica la conversación.")
                with EXAMPLE_LOCK:
                    self._json(set_example_pause(expert_id, conversation_id, suffix == "pause"))
            except (KeyError, ValueError, json.JSONDecodeError) as error:
                self._json({"detail": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/experts":
            try:
                payload = self._payload(10_000)
                name = payload.get("name")
                if not isinstance(name, str):
                    raise ValueError("El nombre debe ser texto.")
                with EXPERT_LOCK:
                    expert = create_expert(name)
                host = self.headers.get("Host", "127.0.0.1:8000")
                self._json({"expert": expert, "link": f"http://{host}/expert/{expert['id']}"}, HTTPStatus.CREATED)
            except (ValueError, json.JSONDecodeError) as error:
                self._json({"detail": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path.startswith("/api/experts/") and parsed.path.endswith("/start"):
            expert_id = unquote(parsed.path.removeprefix("/api/experts/").removesuffix("/start").rstrip("/"))
            try:
                payload = self._payload(10_000)
                participant_code = payload.get("participant_code", "")
                consent = payload.get("consent")
                if not isinstance(participant_code, str) or not isinstance(consent, bool):
                    raise ValueError("Indica el código de participante y la conformidad.")
                with EXPERT_LOCK:
                    self._json(start_expert_conversation(expert_id, participant_code, consent), HTTPStatus.CREATED)
            except KeyError as error:
                self._json({"detail": str(error)}, HTTPStatus.NOT_FOUND)
            except ValueError as error:
                self._json({"detail": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path.startswith("/api/experts/") and parsed.path.endswith("/responses"):
            expert_id, _, _ = unquote(parsed.path.removeprefix("/api/experts/")).partition("/")
            try:
                payload = self._payload(100_000)
                conversation_id = payload.get("conversation_id")
                answer = payload.get("answer")
                coverage = payload.get("coverage", "complete")
                related_questions = payload.get("related_questions", [])
                if not isinstance(conversation_id, str) or not isinstance(answer, str):
                    raise ValueError("La conversación y la respuesta son obligatorias.")
                if not isinstance(coverage, str) or not isinstance(related_questions, list) or not all(isinstance(item, str) for item in related_questions):
                    raise ValueError("La cobertura o las referencias de preguntas no son válidas.")
                with EXPERT_LOCK:
                    self._json(record_expert_response(expert_id, conversation_id, answer, coverage, related_questions))
            except KeyError as error:
                self._json({"detail": str(error)}, HTTPStatus.NOT_FOUND)
            except (ValueError, json.JSONDecodeError) as error:
                self._json({"detail": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path.startswith("/api/experts/") and (parsed.path.endswith("/pause") or parsed.path.endswith("/resume") or parsed.path.endswith("/validate")):
            suffix = next(item for item in ("pause", "resume", "validate") if parsed.path.endswith("/" + item))
            expert_id = unquote(parsed.path.removeprefix("/api/experts/").removesuffix("/" + suffix).rstrip("/"))
            try:
                payload = self._payload(20_000)
                conversation_id = payload.get("conversation_id")
                if not isinstance(conversation_id, str):
                    raise ValueError("Indica la conversación.")
                with EXPERT_LOCK:
                    if suffix == "pause":
                        self._json(pause_expert_conversation(expert_id, conversation_id))
                    elif suffix == "resume":
                        self._json(resume_expert_conversation(expert_id, conversation_id))
                    else:
                        validated = payload.get("validated")
                        corrections = payload.get("corrections", "")
                        ended_early = payload.get("ended_early", False)
                        if not isinstance(validated, bool) or not isinstance(corrections, str) or not isinstance(ended_early, bool):
                            raise ValueError("La validación no es válida.")
                        self._json(validate_expert_conversation(expert_id, conversation_id, validated, corrections, ended_early))
            except KeyError as error:
                self._json({"detail": str(error)}, HTTPStatus.NOT_FOUND)
            except (ValueError, json.JSONDecodeError) as error:
                self._json({"detail": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/consult":
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size > 20_000:
                    raise ValueError("La pregunta es demasiado larga.")
                payload = json.loads(self.rfile.read(size))
                question = payload.get("question") if isinstance(payload, dict) else None
                if not isinstance(question, str):
                    raise ValueError("La pregunta debe ser texto.")
                self._json(consult(question))
            except (ValueError, json.JSONDecodeError) as error:
                self._json({"detail": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path.endswith("/children") and parsed.path.startswith("/api/atoms/"):
            try:
                size = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(size))
                parent_id = unquote(parsed.path.removeprefix("/api/atoms/").removesuffix("/children").rstrip("/"))
                self._json({"atom": atom_payload(create_child(parent_id, payload))}, HTTPStatus.CREATED)
            except KeyError as error:
                self._json({"detail": str(error)}, HTTPStatus.NOT_FOUND)
            except (ValueError, json.JSONDecodeError) as error:
                self._json({"detail": str(error)}, HTTPStatus.BAD_REQUEST)
            except RuntimeError as error:
                self._json({"detail": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if not parsed.path.startswith("/api/atoms/"):
            self._json({"detail": "Ruta no encontrada."}, HTTPStatus.NOT_FOUND)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > 200_000:
                raise ValueError("El cambio es demasiado grande.")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("El cuerpo debe ser un objeto JSON.")
            atom = update_atom(unquote(parsed.path.rsplit("/", 1)[-1]), payload)
        except KeyError as error:
            self._json({"detail": str(error)}, HTTPStatus.NOT_FOUND)
            return
        except (ValueError, json.JSONDecodeError) as error:
            self._json({"detail": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        except RuntimeError as error:
            self._json({"detail": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._json({"atom": atom_payload(atom)})

    def do_PUT(self) -> None:  # noqa: N802 - API de BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        if parsed.path != "/api/expert-protocol":
            self._json({"detail": "Ruta no encontrada."}, HTTPStatus.NOT_FOUND)
            return
        try:
            with EXPERT_LOCK:
                self._json(set_expert_protocol(self._payload(50_000)))
        except (ValueError, json.JSONDecodeError) as error:
            self._json({"detail": str(error)}, HTTPStatus.BAD_REQUEST)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[kb] {format % args}")


def serve(port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Visor listo en http://127.0.0.1:{port}")
    print("Para detenerlo, vuelve a esta Terminal y presiona Control + C.")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")
    serve_parser = sub.add_parser("serve", help="abre el visor local")
    serve_parser.add_argument("--port", type=int, default=8000)
    search_parser = sub.add_parser("search", help="busca con SLDB")
    search_parser.add_argument("term")
    sub.add_parser("check", help="revisa la integridad del índice SLDB")
    args = parser.parse_args()
    if args.command in (None, "serve"):
        serve(getattr(args, "port", 8000))
    elif args.command == "search":
        for atom_id in sldb_find(args.term):
            print(atom_id)
    else:
        raise SystemExit(subprocess.run([SLDB, "stores", "check", "--store", str(STORE)], cwd=ROOT).returncode)


if __name__ == "__main__":
    main()
