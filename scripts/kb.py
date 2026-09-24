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
import subprocess
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / ".sldb"
ATOMS = ROOT / "desk" / "atoms"


@dataclass(frozen=True)
class Atom:
    id: str
    title: str
    question: str
    tags: list[str]
    answer: str
    provenance: str
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
        "path": atom.path,
    }


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
            data = PAGE.encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
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
