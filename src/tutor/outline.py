"""El esquema de una fuente ingerida: tabla de contenidos → capítulos/secciones → páginas y fragmentos.

El PDF trae su tabla de contenidos («Contents … 3.2.1 Actions ….. 19») con páginas IMPRESAS, que no
coinciden con las del PDF (el desfase cambia a lo largo del libro). Por eso el mapa no se calcula
sumando un offset: se leen las entradas de la tabla y se localiza cada encabezado («Chapter 3»,
«3.2.1 Actions») en los `SourceChunk`, en orden. Lo que no se encuentra se interpola por página
impresa entre vecinos encontrados. El resultado se guarda como `SourceOutline`
(`ingest/toc-<source>.md`), generado y regenerable.

    from tutor import outline
    data = outline.build_outline(rows)                 # rows: [{chunk_id, index, page, text}]
    outline.ensure_outline(writer, source_id)          # escribe/actualiza el documento en la KB
    outline.span_for(data, provenance)                 # índices de fragmentos de un capítulo/sección
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

from kb_models.provenance import NAMED_PARTS, Provenance

log = logging.getLogger(__name__)

PREFACE = NAMED_PARTS["prefacio"]
CONTENTS = NAMED_PARTS["tabla de contenidos"]
INTRODUCTION = NAMED_PARTS["introduccion"]
#: Partes con nombre que se resuelven a otra entrada (la introducción del libro es el capítulo 1).
PART_ALIASES = {INTRODUCTION: "1"}
LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "’": "'", "‘": "'"}
_CHAPTER_LINE = re.compile(r"^\s*chapter\s+(\d+)\s*$", re.I)
_CONTENTS_LINE = re.compile(r"^\s*contents\s*$", re.I)
_PREFACE_LINE = re.compile(r"^\s*preface\s*$", re.I)
_ROMAN = re.compile(r"^[ivxl]+$")  # folios en minúscula (vii, viii…); «C Through De» conserva su C
_NUMBER = re.compile(r"^\d+(?:\.\d+)*$")
_DOTS = re.compile(r"^\.+$")
_TRAIL_PAGE = re.compile(r"\s+\d{1,3}$")


def _clean(text: str) -> str:
    for bad, good in LIGATURES.items():
        text = text.replace(bad, good)
    return text


def _norm(text: str) -> str:
    text = _clean(text).lower()
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


# -- tabla de contenidos ------------------------------------------------------------------------


def parse_contents(text: str, *, max_level: int = 3) -> list[dict[str, Any]]:
    """Las entradas de la tabla de contenidos: `[{number, title, level, printed_page}]`.

    Recorre los tokens: número opcional, título hasta una guía de puntos, y los dígitos de la página
    impresa, que el PDF a veces separa con espacios («1 5 1»). La ambigüedad («… 1 2 From Piaget» es
    página 1 seguida del capítulo 2) se resuelve exigiendo que lo que sigue a la página sea un número
    de entrada plausible (capítulo siguiente o sección del capítulo en curso) o un título sin número."""
    tokens = [t for t in _clean(text).split() if not _ROMAN.match(t) and t.lower() != "contents"]
    entries: list[dict[str, Any]] = []
    position = 0
    last_chapter = 0
    while position < len(tokens):
        number: str | None = None
        if _NUMBER.match(tokens[position]) and position + 1 < len(tokens) and not _DOTS.match(tokens[position + 1]):
            number = tokens[position]
            position += 1
        title_tokens: list[str] = []
        while position < len(tokens) and not _DOTS.match(tokens[position]):
            title_tokens.append(tokens[position])
            position += 1
        dots = 0
        while position < len(tokens) and _DOTS.match(tokens[position]):
            dots += len(tokens[position])
            position += 1
        if position >= len(tokens) or dots < 3 or not title_tokens:
            if not title_tokens and number is None:
                position += 1
            continue
        digits: list[str] = []
        while position < len(tokens) and len(digits) < 3 and tokens[position].isdigit() and len(tokens[position]) <= 3:
            digits.append(tokens[position])
            position += 1
        if not digits:
            continue
        chapter = _chapter_of(number) if number else last_chapter
        page, used = _choose_page(digits, tokens[position:], last_chapter if number is None else chapter)
        position -= len(digits) - used
        title = " ".join(title_tokens).strip(" .")
        if title.endswith(".") or _TRAIL_PAGE.search(title):
            title = _TRAIL_PAGE.sub("", title.rstrip("."))
        level = number.count(".") if number else 0
        if level > max_level:
            continue
        entries.append({"number": number or title, "title": title, "level": level, "printed_page": page})
        if number and "." not in number:
            last_chapter = int(number)
    return entries


def _chapter_of(number: str) -> int:
    return int(number.split(".")[0])


def _plausible_next(tokens: list[str], chapter: int) -> bool:
    """Lo que sigue a la página: una entrada numerada coherente, un título sin número, o el final."""
    if not tokens:
        return True
    head = tokens[0]
    if _NUMBER.match(head):
        if len(tokens) < 2 or not tokens[1][:1].isalpha():
            return False
        if "." in head:
            return _chapter_of(head) in (chapter, chapter + 1)
        return int(head) == chapter + 1
    return head[:1].isupper()


def _choose_page(digits: list[str], rest: list[str], chapter: int) -> tuple[int, int]:
    for used in range(1, len(digits) + 1):
        if _plausible_next(digits[used:] + rest, chapter):
            return int("".join(digits[:used])), used
    return int("".join(digits)), len(digits)


# -- localizar encabezados en los fragmentos ----------------------------------------------------


def _lines(rows: list[dict[str, Any]]) -> list[tuple[int, int, str]]:
    """`(índice de fragmento, nº de línea, texto)` de todas las líneas, en orden."""
    out: list[tuple[int, int, str]] = []
    for row in rows:
        for number, line in enumerate(str(row.get("text") or "").splitlines()):
            out.append((int(row["index"]), number, line))
    return out


def _heading_match(entry: dict[str, Any], line: str, next_line: str) -> bool:
    number = entry["number"]
    if _NUMBER.match(number):
        if "." not in number:
            return bool(_CHAPTER_LINE.match(line)) and int(_CHAPTER_LINE.match(line).group(1)) == int(number)  # type: ignore[union-attr]
        stripped = _clean(line).strip()
        if not stripped.startswith(number + " "):
            return False
        rest = stripped[len(number) :]
        return _title_follows(entry["title"], rest, next_line)
    return _norm(line) == _norm(number)


def _title_follows(title: str, rest: str, next_line: str) -> bool:
    wanted = _norm(title).split()[:2]
    got = _norm(rest + " " + next_line).split()[:4]
    if not wanted or not got or wanted[0] != got[0]:
        return False
    return len(wanted) == 1 or wanted[1] in got[1:4]


def locate_entries(entries: list[dict[str, Any]], rows: list[dict[str, Any]], *, start_chunk: int = 0) -> list[dict[str, Any]]:
    """Agrega `chunk_start`/`found` a cada entrada buscando su encabezado desde la última encontrada."""
    lines = _lines(rows)
    cursor = 0
    while cursor < len(lines) and lines[cursor][0] < start_chunk:
        cursor += 1
    located = []
    for entry in entries:
        found = None
        for position in range(cursor, len(lines)):
            chunk, _, line = lines[position]
            next_line = lines[position + 1][2] if position + 1 < len(lines) and lines[position + 1][0] == chunk else ""
            if _heading_match(entry, line, next_line):
                found = (position, chunk)
                break
        if found is not None:
            cursor = found[0] + 1
            located.append({**entry, "chunk_start": found[1], "found": True})
        else:
            located.append({**entry, "chunk_start": None, "found": False})
    return located


def _interpolate(entries: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    """Las entradas sin encabezado localizado reciben el fragmento estimado por página impresa, con
    el desfase (PDF − impresa) del vecino encontrado más cercano, acotado entre vecinos."""
    page_of = {int(r["index"]): int(r.get("page") or 0) for r in rows}
    indexes = sorted(page_of)
    found = [(i, e) for i, e in enumerate(entries) if e["found"]]
    for position, entry in enumerate(entries):
        if entry["found"]:
            continue
        before = [(i, e) for i, e in found if i < position]
        after = [(i, e) for i, e in found if i > position]
        neighbour = (before[-1] if before else after[0] if after else None)
        low = before[-1][1]["chunk_start"] if before else indexes[0]
        high = after[0][1]["chunk_start"] if after else indexes[-1]
        if neighbour is None or entry.get("printed_page") is None or neighbour[1].get("printed_page") is None:
            entry["chunk_start"] = low
            continue
        offset = page_of[neighbour[1]["chunk_start"]] - int(neighbour[1]["printed_page"])
        target = int(entry["printed_page"]) + offset
        candidate = next((i for i in indexes if page_of[i] >= target), indexes[-1])
        entry["chunk_start"] = max(low, min(high, candidate))


def _spans(entries: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    page_of = {int(r["index"]): int(r.get("page") or 0) for r in rows}
    last = max(page_of) if page_of else 0
    for position, entry in enumerate(entries):
        end = last
        for later in entries[position + 1 :]:
            if later["level"] <= entry["level"] and later["chunk_start"] is not None:
                end = max(entry["chunk_start"], later["chunk_start"] - 1)
                break
        entry["chunk_end"] = end
        entry["page_start"] = page_of.get(entry["chunk_start"])
        entry["page_end"] = page_of.get(end)


def build_outline(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Todo el proceso sobre los fragmentos de una fuente (`[{chunk_id, index, page, text}]`):
    `{entries, n_pages, page_offset, n_found, toc_chunks}`."""
    rows = sorted(rows, key=lambda r: int(r["index"]))
    lines = _lines(rows)
    contents_at = next((i for i, (_, _, line) in enumerate(lines) if _CONTENTS_LINE.match(line)), None)
    chapter_one_at = next((i for i, (_, _, line) in enumerate(lines) if (m := _CHAPTER_LINE.match(line)) and int(m.group(1)) == 1 and (contents_at is None or i > contents_at)), None)
    preface_at = next((i for i, (_, _, line) in enumerate(lines) if _PREFACE_LINE.match(line) and (contents_at is None or i < contents_at)), None)
    entries: list[dict[str, Any]] = []
    if contents_at is not None:
        stop = chapter_one_at if chapter_one_at is not None else len(lines)
        toc_text = "\n".join(line for _, _, line in lines[contents_at + 1 : stop])
        entries = parse_contents(toc_text)
    if not entries:  # sin tabla: al menos los capítulos por sus encabezados
        seen: set[int] = set()
        for chunk, _, line in lines:
            match = _CHAPTER_LINE.match(line)
            if match and int(match.group(1)) not in seen:
                seen.add(int(match.group(1)))
                entries.append({"number": match.group(1), "title": f"Chapter {match.group(1)}", "level": 0, "printed_page": None})
    start_chunk = lines[chapter_one_at][0] if chapter_one_at is not None else (lines[contents_at][0] if contents_at is not None else 0)
    located = locate_entries(entries, rows, start_chunk=start_chunk)
    _interpolate(located, rows)
    front: list[dict[str, Any]] = []
    if contents_at is not None:
        preface_chunk = lines[preface_at][0] if preface_at is not None else rows[0]["index"]
        front.append({"number": PREFACE, "title": "Preface", "level": 0, "printed_page": None, "chunk_start": preface_chunk, "found": preface_at is not None})
        front.append({"number": CONTENTS, "title": "Contents", "level": 0, "printed_page": None, "chunk_start": lines[contents_at][0], "found": True})
    located = front + located
    _spans(located, rows)
    page_offset = None
    first = next((e for e in located if e["number"] == "1" and e["found"] and e.get("printed_page")), None)
    if first is not None:
        page_offset = int(first["page_start"]) - int(first["printed_page"])
    return {
        "entries": located,
        "n_pages": max((int(r.get("page") or 0) for r in rows), default=0),
        "page_offset": page_offset,
        "n_found": sum(1 for e in located if e["found"]),
        "toc_chunks": sorted({lines[i][0] for i in range(contents_at, chapter_one_at or contents_at)}) if contents_at is not None else [],
    }


# -- documento en la KB ---------------------------------------------------------------------------


def outline_id(source_id: str) -> str:
    return f"toc-{source_id}"


def chunk_rows(kb: Any, source_id: str) -> list[dict[str, Any]]:
    """Los `SourceChunk` de una fuente como filas planas, por índice."""
    rows = [
        {"chunk_id": d.name, "index": int(d.payload.get("index") or 0), "page": d.payload.get("page"), "text": str(d.payload.get("text") or "")}
        for d in kb.by_model("SourceChunk")
        if d.payload.get("source") == source_id
    ]
    return sorted(rows, key=lambda r: r["index"])


def outline_payload(source_id: str, title: str, data: dict[str, Any]) -> dict[str, Any]:
    entries = [{k: v for k, v in e.items() if k in {"number", "title", "level", "printed_page", "chunk_start", "chunk_end", "page_start", "page_end", "found"}} for e in data["entries"]]
    return {
        "id": outline_id(source_id),
        "title": f"Esquema de {title}",
        "source": source_id,
        "n_pages": int(data["n_pages"]),
        "page_offset": data.get("page_offset"),
        "entries": entries,
        "description": (
            f"Tabla de contenidos de la fuente localizada en sus fragmentos: {len(entries)} entradas, "
            f"{data.get('n_found', 0)} con encabezado encontrado en el texto y el resto interpoladas por página impresa. "
            "Cada entrada abarca los fragmentos desde su encabezado hasta la siguiente entrada de su nivel."
        ),
    }


def ensure_outline(writer: Any, source_id: str, *, force: bool = False) -> dict[str, Any] | None:
    """Escribe (o reutiliza) el `SourceOutline` de la fuente; None si la fuente no tiene fragmentos."""
    from tutor import kb_build
    from tutor.authoring import FOLDERS

    kb = writer.kb()
    existing = writer.find(outline_id(source_id)) if "SourceOutline" in writer.registered_models() else None
    if existing is not None and not force:
        return dict(existing.payload)
    rows = chunk_rows(kb, source_id)
    if not rows:
        return None
    source = writer.find(source_id)
    title = str((source.payload.get("title") if source is not None else None) or source_id)
    payload = outline_payload(source_id, title, build_outline(rows))
    writer.write(kb_build.Doc("SourceOutline", f"{FOLDERS['SourceOutline']}/{outline_id(source_id)}.md", payload, name=payload["id"]))
    return payload


def load_outline(kb: Any, source_id: str) -> dict[str, Any] | None:
    for document in kb.by_model("SourceOutline"):
        if document.payload.get("source") == source_id:
            return dict(document.payload)
    return None


# -- resolver una procedencia a fragmentos ------------------------------------------------------


def entry_for(outline: dict[str, Any], number: str) -> dict[str, Any] | None:
    number = PART_ALIASES.get(number, number)
    return next((e for e in outline.get("entries") or [] if str(e.get("number")) == number), None)


def span_for(outline: dict[str, Any] | None, provenance: Provenance) -> tuple[list[tuple[int, int]], list[str]]:
    """Los tramos `(chunk_start, chunk_end)` que la procedencia nombra (secciones si las hay, si no el
    capítulo; partes con nombre aparte) y las entradas que no se pudieron resolver."""
    if outline is None:
        return [], []
    spans: list[tuple[int, int]] = []
    missing: list[str] = []
    wanted = list(provenance.numeric_sections) or ([str(provenance.chapter)] if provenance.chapter is not None else [])
    wanted += provenance.named_parts
    for number in wanted:
        entry = entry_for(outline, number)
        if entry is None or entry.get("chunk_start") is None:
            missing.append(number)
            continue
        spans.append((int(entry["chunk_start"]), int(entry["chunk_end"] if entry.get("chunk_end") is not None else entry["chunk_start"])))
    if missing and provenance.chapter is not None and not any(n == str(provenance.chapter) for n in wanted):
        entry = entry_for(outline, str(provenance.chapter))  # secciones desconocidas: todo el capítulo
        if entry is not None and entry.get("chunk_start") is not None:
            spans.append((int(entry["chunk_start"]), int(entry.get("chunk_end") or entry["chunk_start"])))
    return spans, missing


__all__ = [
    "build_outline",
    "chunk_rows",
    "ensure_outline",
    "entry_for",
    "load_outline",
    "locate_entries",
    "outline_id",
    "outline_payload",
    "parse_contents",
    "span_for",
]
