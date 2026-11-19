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
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / ".sldb"
ATOMS = ROOT / "desk" / "atoms"
WEB = ROOT / "web"
SUGGESTIONS = ROOT / "knowledge" / "didactic-suggestions"
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

    def do_GET(self) -> None:  # noqa: N802 - API de BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        if parsed.path == "/":
            data = (WEB / "index.html").read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if parsed.path.startswith("/web/"):
            filename = parsed.path.removeprefix("/web/")
            content_types = {"theme.css": "text/css; charset=utf-8", "hierarchy.js": "text/javascript; charset=utf-8", "mindmap.js": "text/javascript; charset=utf-8", "mindmap.css": "text/css; charset=utf-8"}
            if filename in content_types:
                data = (WEB / filename).read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_types[filename])
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
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
