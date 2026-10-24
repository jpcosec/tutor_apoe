"""Ingesta de fuentes SIN LLM: el texto entra, se fragmenta y se guarda; proponer átomos es
tarea del cliente MCP (el LLM), que recibe los fragmentos y cita su `chunk_id` en `provenance`.

    from tutor import ingest
    result = ingest.ingest_text("demo", "Capítulo 1", texto)      # {source_id, chunks:[{chunk_id, text, start, end}]}
    ingest.ingest_file("demo", "docs/fuente.pdf")                  # .md/.txt siempre; .pdf si hay pypdf
    ingest.get_chunk("demo", "source-capitulo-1-chunk-0")

Cada fuente es un `SourceDoc` (`ingest/sources/<source_id>.md`) y cada fragmento un `SourceChunk`
(`ingest/chunks/<source_id>/<chunk_id>.md`), ambos del esquema `kb_models.ingest`. No entran al
índice de embeddings (`kb.yaml` indexa solo `KnowledgeAtom`) ni a la proyección del tutor
(`projection-tutor` nombra `KnowledgeAtom` y `BranchNode`): son materia prima, no conocimiento.

Fragmentación: por párrafos (líneas en blanco), juntando párrafos hasta `chunk_chars`; un párrafo
más largo que el límite se parte por oraciones y, si hace falta, por caracteres. Los offsets
`start`/`end` apuntan al texto original.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tutor import authoring, kb_build
from tutor.authoring import FOLDERS, AuthoringError, KbWriter, demote_headings, slugify

DEFAULT_CHUNK_CHARS = 1200
MIN_CHUNK_CHARS = 200
TEXT_SUFFIXES = {".md", ".txt", ".markdown", ".text"}
PDF_SUFFIXES = {".pdf"}
_PARAGRAPH = re.compile(r"\n\s*\n")
_SENTENCE = re.compile(r"(?<=[.!?…])\s+")


# -- fragmentar ---------------------------------------------------------------------------


def chunk_text(text: str, chunk_chars: int = DEFAULT_CHUNK_CHARS) -> list[dict[str, Any]]:
    """`[{index, text, start, end}]`: párrafos agrupados hasta `chunk_chars`, offsets sobre `text`."""
    if chunk_chars < MIN_CHUNK_CHARS:
        raise AuthoringError(f"chunk_chars demasiado chico: {chunk_chars}", f"usa al menos {MIN_CHUNK_CHARS}")
    pieces: list[tuple[int, int]] = []
    for start, end in _spans(text, _PARAGRAPH):
        if end - start <= chunk_chars:
            pieces.append((start, end))
            continue
        for s_start, s_end in _spans(text[start:end], _SENTENCE, offset=start):
            if s_end - s_start <= chunk_chars:
                pieces.append((s_start, s_end))
            else:
                pieces.extend((p, min(p + chunk_chars, s_end)) for p in range(s_start, s_end, chunk_chars))
    chunks: list[dict[str, Any]] = []
    current: tuple[int, int] | None = None
    for start, end in pieces:
        if current is None:
            current = (start, end)
        elif end - current[0] <= chunk_chars:
            current = (current[0], end)
        else:
            chunks.append(current)
            current = (start, end)
    if current is not None:
        chunks.append(current)
    return [{"index": i, "text": text[s:e].strip(), "start": s, "end": e} for i, (s, e) in enumerate(chunks) if text[s:e].strip()]


def _spans(text: str, separator: re.Pattern[str], offset: int = 0) -> list[tuple[int, int]]:
    """Los tramos no vacíos entre separadores, como offsets absolutos (recortando blancos)."""
    spans: list[tuple[int, int]] = []
    position = 0
    for match in [*separator.finditer(text), None]:
        end = match.start() if match is not None else len(text)
        piece = text[position:end]
        stripped = piece.strip()
        if stripped:
            lead = len(piece) - len(piece.lstrip())
            spans.append((offset + position + lead, offset + position + lead + len(stripped)))
        position = match.end() if match is not None else end
    return spans


# -- guardar ------------------------------------------------------------------------------


def ingest_text(
    kb_id: str,
    title: str,
    text: str,
    *,
    source_path: str | None = None,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    source_id: str | None = None,
    root: Path | str | None = None,
) -> dict[str, Any]:
    """Guarda `text` como `SourceDoc` + `SourceChunk`s y devuelve los fragmentos para que el cliente
    proponga átomos. Si la fuente (mismo `source_id`, derivado del título) ya existía, la reemplaza."""
    from kb_models.ingest import SourceChunk, SourceDoc

    text = text.replace("\r\n", "\n")
    if not text.strip():
        raise AuthoringError("el texto está vacío", "pasa el contenido de la fuente")
    if not str(title).strip():
        raise AuthoringError("la fuente necesita title", "un título corto (libro, capítulo, URL…)")
    source_id = (source_id or slugify(title, "source-")).strip()
    authoring._check_identifier(source_id, "source_id")
    writer = KbWriter.open(kb_id, root)
    writer.ensure_model("SourceDoc")
    writer.ensure_model("SourceChunk")
    existing = writer.find(source_id)
    if existing is not None and existing.model != "SourceDoc":
        raise AuthoringError(f"{source_id!r} ya existe como {existing.model}", "usa otro título o pasa source_id")
    if existing is not None:
        _delete_source(writer, source_id)
    chunks = chunk_text(text, chunk_chars)
    source_payload = {
        "id": source_id,
        "title": str(title).strip(),
        "path": source_path,
        "n_chunks": len(chunks),
        "description": f"Fuente ingerida por `tutor.ingest` en {len(chunks)} fragmentos de hasta {chunk_chars} caracteres (por párrafos).",
    }
    authoring._validate(SourceDoc, source_payload, "fuente")
    docs = [kb_build.Doc("SourceDoc", f"{FOLDERS['SourceDoc']}/{source_id}.md", source_payload, name=source_id)]
    out: list[dict[str, Any]] = []
    for chunk in chunks:
        chunk_id = f"{source_id}-chunk-{chunk['index']}"
        payload = {
            "id": chunk_id,
            "title": f"{title.strip()} · fragmento {chunk['index']}",
            "source": source_id,
            "index": chunk["index"],
            "start": chunk["start"],
            "end": chunk["end"],
            "text": demote_headings(chunk["text"]),
        }
        authoring._validate(SourceChunk, payload, "fragmento")
        docs.append(kb_build.Doc("SourceChunk", f"{FOLDERS['SourceChunk']}/{source_id}/{chunk_id}.md", payload, name=chunk_id))
        out.append({"chunk_id": chunk_id, "index": chunk["index"], "text": chunk["text"], "start": chunk["start"], "end": chunk["end"]})
    for doc in docs:
        writer.write(doc)
    writer.refresh(index=False)
    return {"source_id": source_id, "title": title.strip(), "path": source_path, "n_chunks": len(out), "replaced": existing is not None, "chunks": out}


def ingest_file(kb_id: str, path: str | Path, *, title: str | None = None, chunk_chars: int = DEFAULT_CHUNK_CHARS, root: Path | str | None = None) -> dict[str, Any]:
    """`ingest_text` sobre un archivo: `.md`/`.txt` siempre; `.pdf` si `pypdf` está instalado."""
    file = Path(path).expanduser()
    if not file.is_file():
        raise AuthoringError(f"no existe el archivo {file}", "pasa una ruta absoluta o relativa al directorio del servidor")
    suffix = file.suffix.lower()
    if suffix in TEXT_SUFFIXES or suffix == "":
        text = file.read_text(encoding="utf-8", errors="replace")
    elif suffix in PDF_SUFFIXES:
        text = read_pdf(file)
    else:
        raise AuthoringError(f"formato no soportado: {suffix}", "usa .md, .txt o .pdf (con pypdf instalado)")
    return ingest_text(kb_id, title or file.stem.replace("_", " ").replace("-", " ").strip(), text, source_path=str(file), chunk_chars=chunk_chars, root=root)


def read_pdf(file: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise AuthoringError("pypdf no está instalado", "pip install pypdf, o convierte el PDF a .txt/.md") from error
    reader = PdfReader(str(file))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n\n".join(p for p in pages if p)


def get_chunk(kb_id: str, chunk_id: str, root: Path | str | None = None) -> dict[str, Any]:
    """Un fragmento por id: `{chunk_id, source, index, start, end, text}`."""
    writer = KbWriter.open(kb_id, root)
    document = writer.require(chunk_id, "fragmento")
    if document.model != "SourceChunk":
        raise AuthoringError(f"{chunk_id!r} es un {document.model}, no un fragmento", "los fragmentos se llaman <source_id>-chunk-<n>")
    payload = document.payload
    return {"chunk_id": document.name, "source": payload.get("source"), "index": payload.get("index"), "start": payload.get("start"), "end": payload.get("end"), "text": payload.get("text")}


def list_sources(kb_id: str, root: Path | str | None = None) -> list[dict[str, Any]]:
    """Las fuentes ingeridas: `[{source_id, title, path, n_chunks}]`."""
    writer = KbWriter.open(kb_id, root)
    if "SourceDoc" not in writer.registered_models():
        return []
    return [
        {"source_id": d.name, "title": d.payload.get("title"), "path": d.payload.get("path"), "n_chunks": d.payload.get("n_chunks")}
        for d in writer.kb().by_model("SourceDoc")
    ]


def delete_source(kb_id: str, source_id: str, root: Path | str | None = None) -> dict[str, Any]:
    """Borra una fuente y todos sus fragmentos (los átomos que la citan en `provenance` quedan)."""
    writer = KbWriter.open(kb_id, root)
    document = writer.require(source_id, "fuente")
    if document.model != "SourceDoc":
        raise AuthoringError(f"{source_id!r} es un {document.model}, no una fuente", "usa list_sources")
    removed = _delete_source(writer, source_id)
    writer.refresh(index=False)
    return {"deleted": source_id, "chunks_removed": removed}


def _delete_source(writer: KbWriter, source_id: str) -> int:
    chunks = [d.name for d in writer.kb().by_model("SourceChunk") if d.payload.get("source") == source_id]
    for name in chunks:
        writer.delete(name)
    writer.delete(source_id)
    return len(chunks)


__all__ = ["chunk_text", "delete_source", "get_chunk", "ingest_file", "ingest_text", "list_sources", "read_pdf"]
