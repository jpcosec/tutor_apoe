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
import json
import re
import subprocess
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / ".sldb"
ATOMS = ROOT / "desk" / "atoms"
WEB = ROOT / "web"


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
        "sldb", "find", term, "--in", "both", "--type", "doc",
        "--store", str(STORE), "--pythonpath", str(ROOT), "--format", "json",
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if result.returncode:
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
        ["sldb", "stores", "update", "--store", str(STORE), "--pythonpath", str(ROOT)],
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
    refreshed = subprocess.run(["sldb", "stores", "update", "--store", str(STORE), "--pythonpath", str(ROOT)], cwd=ROOT, text=True, capture_output=True)
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
            content_types = {"mindmap.js": "text/javascript; charset=utf-8", "mindmap.css": "text/css; charset=utf-8"}
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
        raise SystemExit(subprocess.run(["sldb", "stores", "check", "--store", str(STORE)], cwd=ROOT).returncode)


if __name__ == "__main__":
    main()
