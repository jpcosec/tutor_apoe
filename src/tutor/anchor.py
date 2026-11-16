"""Anclaje: de «cap. 3 §3.2.3» a los fragmentos del PDF que de verdad respaldan cada átomo.

Para cada átomo con procedencia `book`:

1. Candidatos: los `SourceChunk` dentro del tramo que su procedencia nombra (secciones si las hay,
   si no el capítulo; partes con nombre), según el `SourceOutline` (`tutor.outline`). Sin esquema o
   sin tramo resoluble, todo el libro.
2. Ranking por similitud de embedding (`HashEmbedder`, el mismo índice cacheado del compilador)
   entre título + respuesta del átomo y el texto del fragmento; pasan los `top_k` mejores.
3. Confirmación con Jev (`compiler.grounded_noul`: «¿este fragmento respalda la afirmación?»):
   se conservan hasta `keep` fragmentos con noul ≥ `threshold`, con sus páginas reales y la
   oración del mejor fragmento más parecida a la respuesta (`excerpt`). Sin respaldo, el átomo
   queda `anchored=False` (*unanchored*) con `chunk_ids=[]`.

El resultado se cachea en `<kb>/.cache/anchors.json` por hash de (átomo, candidatos, parámetros)
para no pagar Jev dos veces; `kb_build` lo corre como paso (`--anchor/--no-anchor`) y la CLI lo
expone como `tutor kb anchor`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kb_models.provenance import Provenance, ProvenanceKind
from tutor import outline as outline_mod
from tutor import world
from tutor.compiler import CACHE_DIR, ChunkIndex, _cosine, chunk_index, grounded_noul
from tutor.embedding import HashEmbedder

log = logging.getLogger(__name__)

THRESHOLD = 0.5
TOP_K = 6
KEEP = 3
CACHE_FILE = "anchors.json"
EXCERPT_MAX = 320
MIN_SENTENCE = 25
_SENTENCES = re.compile(r"(?<=[.!?])\s+")
#: Una línea que es un encabezado numerado («3.2.3 Encapsulation and Objects»): no forma parte de ninguna oración.
_HEADING = re.compile(r"^\d+(?:\.\d+)+\s+[A-Z][^.]{0,70}$")


@dataclass
class AnchorResult:
    """Lo que el anclaje decidió sobre un átomo."""

    atom_id: str
    anchored: bool | None
    chunk_ids: list[str] = field(default_factory=list)
    nouls: list[float] = field(default_factory=list)
    candidates: list[tuple[str, float, float | None]] = field(default_factory=list)
    pages: list[int] | None = None
    excerpt: str | None = None
    missing: list[str] = field(default_factory=list)
    cached: bool = False
    jev_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "atom_id": self.atom_id,
            "anchored": self.anchored,
            "chunk_ids": list(self.chunk_ids),
            "nouls": list(self.nouls),
            "candidates": [list(c) for c in self.candidates],
            "pages": self.pages,
            "excerpt": self.excerpt,
            "missing": list(self.missing),
            "cached": self.cached,
            "jev_calls": self.jev_calls,
        }


# -- caché ------------------------------------------------------------------------------------------


class AnchorCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, dict[str, Any]] = {}
        self.dirty = False
        if path.is_file():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                log.warning("caché de anclaje ilegible, se regenera: %s", path)

    def get(self, key: str) -> dict[str, Any] | None:
        return self.data.get(key)

    def put(self, key: str, value: dict[str, Any]) -> None:
        self.data[key] = value
        self.dirty = True

    def save(self) -> None:
        if not self.dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
        self.dirty = False


def cache_key(atom_id: str, claim: str, candidates: list[str], index: ChunkIndex, *, threshold: float, keep: int) -> str:
    texts = "\n".join(f"{c}\t{hashlib.sha1(index.chunks[c]['text'].encode('utf-8')).hexdigest()}" for c in candidates)
    raw = f"{atom_id}\n{claim}\n{texts}\n{threshold}\n{keep}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# -- candidatos, ranking, excerpt -------------------------------------------------------------------


def candidate_ids(index: ChunkIndex, source: str | None, spans: list[tuple[int, int]]) -> list[str]:
    """Los chunk_ids de la fuente dentro de los tramos `(chunk_start, chunk_end)`; todos si no hay tramos."""
    rows = [r for r in index.chunks.values() if source is None or r.get("source") == source]
    if not spans:
        return [r["chunk_id"] for r in rows]
    wanted = {r["chunk_id"] for r in rows for start, end in spans if start <= int(r.get("index") or -1) <= end}
    return [r["chunk_id"] for r in rows if r["chunk_id"] in wanted]


def rank_candidates(index: ChunkIndex, vector: list[float], ids: list[str], top_k: int) -> list[tuple[str, float]]:
    position = {chunk_id: i for i, chunk_id in enumerate(index.ids)}
    scored = [(chunk_id, round(_cosine(vector, index.vectors[position[chunk_id]]), 4)) for chunk_id in ids if chunk_id in position]
    scored.sort(key=lambda s: (-s[1], s[0]))
    return scored[: max(1, top_k)]


def best_sentence(text: str, vector: list[float], embedder: Any) -> str | None:
    """La oración del fragmento más parecida (coseno) a la respuesta, con blancos normalizados."""
    blocks: list[str] = []
    for line in text.splitlines():
        if _HEADING.match(line.strip()):
            blocks.append("")
        elif blocks:
            blocks[-1] = f"{blocks[-1]}\n{line}" if blocks[-1] else line
        else:
            blocks.append(line)
    sentences = [" ".join(s.split()) for block in blocks for s in _SENTENCES.split(block) if len(s.strip()) >= MIN_SENTENCE]
    if not sentences:
        flat = " ".join(text.split())
        return flat[:EXCERPT_MAX] or None
    vectors = embedder.embed(sentences)
    best = max(range(len(sentences)), key=lambda i: _cosine(vector, vectors[i]))
    return sentences[best][:EXCERPT_MAX]


# -- un átomo -----------------------------------------------------------------------------------------


def anchor_atom(
    atom_id: str,
    claim: str,
    items: list[Provenance],
    *,
    index: ChunkIndex,
    outline: dict[str, Any] | None,
    embedder: Any,
    client: Any | None,
    cache: AnchorCache | None = None,
    threshold: float = THRESHOLD,
    top_k: int = TOP_K,
    keep: int = KEEP,
    force: bool = False,
) -> tuple[list[Provenance], AnchorResult]:
    """Devuelve la procedencia actualizada (chunk_ids, nouls, pages, excerpt, anchored) y el detalle."""
    book = [i for i in items if i.kind == ProvenanceKind.BOOK]
    if not book or not index.ids:
        return items, AnchorResult(atom_id, None)
    spans: list[tuple[int, int]] = []
    missing: list[str] = []
    for item in book:
        found, lost = outline_mod.span_for(outline, item)
        spans.extend(found)
        missing.extend(lost)
    source = book[0].source
    pool = candidate_ids(index, source, spans) or candidate_ids(index, source, [])
    vector = embedder.embed([claim])[0]
    ranked = rank_candidates(index, vector, pool, top_k)
    key = cache_key(atom_id, claim, [c for c, _ in ranked], index, threshold=threshold, keep=keep)
    cached = None if force or cache is None else cache.get(key)
    jev_calls = 0
    if cached is not None:
        nouls = {c: n for c, n in cached["nouls"].items()}
    elif client is None:
        nouls = {}
    else:
        with ThreadPoolExecutor(max_workers=max(1, min(6, len(ranked)))) as executor:
            values = list(executor.map(lambda c: grounded_noul(client, claim, index.chunks[c[0]]["text"]), ranked))
        jev_calls = len(ranked)
        nouls = {c: v for (c, _), v in zip(ranked, values, strict=False) if v is not None}
        if cache is not None and len(nouls) == len(ranked):
            cache.put(key, {"atom_id": atom_id, "nouls": nouls, "ranked": ranked})
    evaluated = bool(nouls)
    chosen = sorted(((c, n) for c, n in nouls.items() if n >= threshold), key=lambda cn: (-cn[1], cn[0]))[: max(1, keep)]
    chosen_ids = [c for c, _ in chosen]
    pages_of = {c: index.chunks[c].get("page") for c in chosen_ids}
    all_pages = sorted(int(p) for p in pages_of.values() if p)
    excerpt = best_sentence(index.chunks[chosen_ids[0]]["text"], vector, embedder) if chosen_ids else None
    updated: list[Provenance] = []
    excerpt_given = False
    for item in items:
        if item.kind != ProvenanceKind.BOOK:
            updated.append(item)
            continue
        own_spans, _ = outline_mod.span_for(outline, item)
        mine = [c for c in chosen_ids if not own_spans or any(s <= int(index.chunks[c].get("index") or -1) <= e for s, e in own_spans)]
        if not mine and chosen_ids and len(book) == 1:
            mine = list(chosen_ids)
        pages = sorted(int(pages_of[c]) for c in mine if pages_of.get(c))
        updated.append(
            item.model_copy(
                update={
                    "chunk_ids": mine,
                    "nouls": [round(float(nouls[c]), 3) for c in mine],
                    "pages": [pages[0], pages[-1]] if pages else None,
                    "excerpt": excerpt if (mine and not excerpt_given and chosen_ids[0] in mine) else None,
                    "anchored": (bool(mine) if evaluated else None),
                }
            )
        )
        if mine and chosen_ids[0] in mine:
            excerpt_given = True
    result = AnchorResult(
        atom_id,
        anchored=(bool(chosen_ids) if evaluated else None),
        chunk_ids=chosen_ids,
        nouls=[round(float(nouls[c]), 3) for c in chosen_ids],
        candidates=[(c, s, (round(float(nouls[c]), 3) if c in nouls else None)) for c, s in ranked],
        pages=[all_pages[0], all_pages[-1]] if all_pages else None,
        excerpt=excerpt,
        missing=missing,
        cached=cached is not None,
        jev_calls=jev_calls,
    )
    return updated, result


# -- toda la KB ---------------------------------------------------------------------------------------


def anchor_kb(
    kb_id: str,
    root: Path | str | None = None,
    *,
    writer: Any | None = None,
    client: Any | None = None,
    embedder: Any | None = None,
    threshold: float = THRESHOLD,
    top_k: int = TOP_K,
    keep: int = KEEP,
    force: bool = False,
    write: bool = True,
    refresh: bool = True,
    only: set[str] | None = None,
) -> dict[str, Any]:
    """Ancla todos los `KnowledgeAtom` de la KB (o los de `only`) y reescribe su procedencia.
    `client=None` usa Jev si hay `TYPESAFE_API_KEY` (si no, solo la caché: lo no cacheado queda sin
    evaluar). Devuelve el informe: conteos, distribución de nouls, llamadas a Jev, detalle por átomo."""
    from kb_models.apos import provenance_items
    from tutor import kb_build
    from tutor.authoring import KbWriter
    from tutor.selector_jev import default_client

    writer = writer or KbWriter.open(kb_id, root)
    embedder = embedder or HashEmbedder()
    index = chunk_index(writer.kb_id, writer.root.parent, embedder=embedder, writer=writer)
    kb = writer.kb()
    outlines: dict[str, dict[str, Any] | None] = {}
    for document in kb.by_model("SourceDoc") if "SourceDoc" in writer.registered_models() else []:
        outlines[document.name] = outline_mod.ensure_outline(writer, document.name)
    kb = writer.kb()
    client = client if client is not None else default_client()
    cache = AnchorCache(writer.root / CACHE_DIR / CACHE_FILE)
    results: list[AnchorResult] = []
    docs: list[Any] = []
    for document in kb.by_model(world.KNOWLEDGE_MODEL):
        if only is not None and document.name not in only:
            continue
        payload = dict(document.payload)
        items = provenance_items(payload)
        claim = f"{payload.get('title') or document.name}. {payload.get('answer') or ''}".strip()
        source = next((i.source for i in items if i.kind == ProvenanceKind.BOOK and i.source), None)
        updated, result = anchor_atom(
            document.name, claim, items, index=index, outline=outlines.get(source) if source else None, embedder=embedder,
            client=client, cache=cache, threshold=threshold, top_k=top_k, keep=keep, force=force,
        )
        results.append(result)
        if result.anchored is None and not any(i.kind == ProvenanceKind.BOOK for i in items):
            continue
        new_payload = {**payload, "provenance": [i.model_dump(mode="json") for i in updated]}
        if new_payload["provenance"] != [i.model_dump(mode="json") for i in items]:  # comparar normalizado: sldb omite los None al leer
            docs.append(kb_build.Doc(document.model, document.path, new_payload, name=document.name))
    cache.save()
    if write and docs:
        writer.write_many(docs)
        if refresh:
            writer.refresh(index=False)
    return report(results, written=len(docs) if write else 0, jev=client is not None)


def report(results: list[AnchorResult], *, written: int = 0, jev: bool = True) -> dict[str, Any]:
    anchored = [r for r in results if r.anchored is True]
    unanchored = [r for r in results if r.anchored is False]
    pending = [r for r in results if r.anchored is None and r.candidates]
    skipped = [r for r in results if r.anchored is None and not r.candidates]
    nouls = sorted(n for r in results for _, _, n in r.candidates if n is not None)
    buckets = {"<0.25": 0, "0.25–0.5": 0, "0.5–0.75": 0, "≥0.75": 0}
    for n in nouls:
        buckets["<0.25" if n < 0.25 else "0.25–0.5" if n < 0.5 else "0.5–0.75" if n < 0.75 else "≥0.75"] += 1
    return {
        "n_atoms": len(results),
        "anchored": len(anchored),
        "unanchored": len(unanchored),
        "pending": len(pending),
        "skipped": len(skipped),
        "jev": jev,
        "jev_calls": sum(r.jev_calls for r in results),
        "cached": sum(1 for r in results if r.cached),
        "written": written,
        "nouls": {"n": len(nouls), "buckets": buckets, "median": (nouls[len(nouls) // 2] if nouls else None)},
        "unanchored_ids": [r.atom_id for r in unanchored],
        "pending_ids": [r.atom_id for r in pending],
        "atoms": [r.to_dict() for r in results],
    }


__all__ = ["AnchorCache", "AnchorResult", "KEEP", "THRESHOLD", "TOP_K", "anchor_atom", "anchor_kb", "best_sentence", "candidate_ids", "rank_candidates", "report"]
