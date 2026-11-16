"""El compilador: átomos nuevos a pedido, con procedencia real, que no tocan al tutor hasta aprobarse.

Flujo: pedir → proponer → revisar → aprobar.

    from tutor import compiler
    compiler.ingest_source("apos", "sources/Arnon.pdf")            # SourceDoc + SourceChunk con página
    result = compiler.compile("apos", "el ciclo ACE y sus actividades", max_atoms=5)
    result.proposals, result.rejected, result.usage                 # propuestos escritos en proposed/
    compiler.list_proposed("apos")                                  # [{id, title, status, grounded, …}]
    compiler.approve("apos", "atom-…")                              # → KnowledgeAtom con child_of
    compiler.reject("apos", "atom-…", why="redundante")
    compiler.gaps("apos", ["¿qué es la tematización?"])             # noul máximo de la mesa por pregunta

Piezas:

- Índice de fragmentos (`chunk_index`, `search_chunks`): los `SourceChunk` están fuera del índice de
  `kb` (que indexa solo `KnowledgeAtom`), así que se embeben aparte con `HashEmbedder` y se cachean
  en `<kb>/.cache/chunks-<embedder>.json`, invalidado por el hash de contenido de los fragmentos.
- Estado «propuesto»: un `ProposedAtom` (`kb_models.proposed`) por átomo candidato, en `proposed/`.
  No es subclase de `KnowledgeAtom`, así que `projection-tutor` (que nombra `KnowledgeAtom` y
  `BranchNode`) no lo deja ver y el índice no lo embebe: `tutor.agent.build_context` nunca lo trae.
  `approve` lo borra y escribe un `KnowledgeAtom` con el mismo id y su `child_of` (`upsert_atom`).
- El agente (`compile`): `pydantic_ai.Agent` con `output_type=list[AtomProposal]` y tools de lectura
  (`search_chunks`, `search_atoms`, `list_branches`, `get_atom`, `get_chunk`). Post-proceso en código
  (`review`): parent inexistente, chunks inexistentes, duplicado (coseno hash > 0.9 con un átomo
  existente) → rechazado con razones; un Noul de Jev opcional marca `grounded`.
- `gaps`: para cada pregunta, el noul máximo de la mesa (`JevSelector.score` sobre el top-30 por
  embedding); si queda bajo 0.5 es candidata a compilar.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from tutor import authoring, ingest, kb_build, world
from tutor.authoring import FOLDERS, AuthoringError, KbWriter, demote_headings, slugify
from tutor.embedding import HashEmbedder

log = logging.getLogger(__name__)

MODEL = "ProposedAtom"
STATUSES = ("proposed", "approved", "rejected")
QUESTIONS = authoring.QUESTIONS
TITLE_MAX = 90
ANSWER_MAX_WORDS = 80
QUOTE_MAX_WORDS = 60
#: Coseno (embedding hash) a partir del cual una propuesta se considera duplicado de un átomo existente.
DUPLICATE_THRESHOLD = 0.9
#: Coseno a partir del cual un átomo existente se anota en `similar_to`.
SIMILAR_THRESHOLD = 0.5
#: Noul mínimo para considerar que la mesa cubre una pregunta (`gaps`) o que un fragmento respalda una respuesta.
GAP_THRESHOLD = 0.5
GROUNDED_THRESHOLD = 0.5
GAP_POOL = 30
CACHE_DIR = ".cache"
#: Peticiones al modelo por compilación: la primera más las iteraciones con tools.
MAX_REQUESTS = 16
#: Tope de tokens de salida por petición: `TUTOR_COMPILE_MAX_TOKENS` o, si no, el del tutor
#: (`TUTOR_MAX_TOKENS`, 1500). OpenRouter reserva `max_tokens` contra el crédito disponible, así que
#: un tope alto falla con 402 aunque la respuesta real sea corta; 5 átomos caben en ~1200 tokens.
ENV_MAX_TOKENS = "TUTOR_COMPILE_MAX_TOKENS"
ENV_MODEL = "TUTOR_MODEL"
COMPILER_MARK = "tutor.compiler"
TAG = re.compile(r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_.-]*$")

GROUNDED_NAME = "respaldado"
GROUNDED_INSTRUCTIONS = (
    "`atom_answer` is a one-claim knowledge atom (Spanish) that a compiler proposed from a source text "
    "about APOS theory (Arnon et al. 2014). `cited_fragment` is the source passage it cites. Is the claim "
    "in `atom_answer` directly supported by `cited_fragment`?"
)
GROUNDED_CRITERIA = {
    "true": "The fragment states or clearly implies the same claim; the atom adds no facts the fragment does not contain.",
    "false": "The fragment is about something else, only shares vocabulary, or the atom adds, generalizes or distorts claims.",
}


# --------------------------------------------------------------------------------------------
# Esquema de salida del agente
# --------------------------------------------------------------------------------------------


class Provenance(BaseModel):
    """De dónde sale la afirmación: fragmentos reales, cita textual, lugar en la fuente."""

    chunk_ids: list[str] = Field(min_length=1, description="Ids de fragmentos (`<source>-chunk-<n>`) leídos con search_chunks/get_chunk que respaldan la respuesta.")
    quote: str = Field(description="Cita textual corta copiada del fragmento (en su idioma original), que respalda la respuesta.")
    where: str = Field(default="", description="Página o sección de la fuente, p. ej. 'p. 42' o 'cap. 5, §5.2'.")

    @field_validator("quote")
    @classmethod
    def _short_quote(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("la cita no puede estar vacía")
        if len(value.split()) > QUOTE_MAX_WORDS:
            raise ValueError(f"la cita debe tener como máximo {QUOTE_MAX_WORDS} palabras")
        return value


class AtomProposal(BaseModel):
    """Un átomo candidato tal como lo propone el modelo."""

    title: str = Field(max_length=TITLE_MAX, description="La afirmación en una frase corta (≤ 90 caracteres), en español.")
    question: Literal["what", "why", "how", "how_not", "when", "where", "for_whom"] = Field(description="La única pregunta 5W1H que responde.")
    answer: str = Field(description="Una sola afirmación, en español, ≤ 80 palabras, fiel al fragmento citado.")
    provenance: Provenance
    tags: list[str] = Field(description="Tags `namespace:valor` en minúsculas: system:<kb> siempre; topic:<concepto>; layer:theory|pedagogy|example; domain:<dominio>.")
    parent: str = Field(description="Id de una rama (BranchNode) existente, de list_branches.")
    rationale: str = Field(description="Por qué hace falta este átomo: qué pregunta o vacío cubre que la KB no cubría.")

    @field_validator("title", "answer", "rationale")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("no puede estar vacío")
        return value

    @field_validator("answer")
    @classmethod
    def _short_answer(cls, value: str) -> str:
        if len(value.split()) > ANSWER_MAX_WORDS:
            raise ValueError(f"la respuesta debe tener como máximo {ANSWER_MAX_WORDS} palabras (una sola afirmación)")
        return value

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: list[str]) -> list[str]:
        cleaned = [t.strip().lower() for t in value if t.strip()]
        bad = [t for t in cleaned if not TAG.match(t)]
        if bad:
            raise ValueError(f"tags inválidos (deben ser namespace:valor en minúsculas): {bad}")
        return cleaned


@dataclass
class Review:
    """El veredicto del post-proceso sobre una propuesta."""

    id: str
    proposal: AtomProposal
    reasons: list[str] = field(default_factory=list)
    similar_to: list[tuple[str, float]] = field(default_factory=list)
    grounded: bool | None = None
    grounded_noul: float | None = None

    @property
    def accepted(self) -> bool:
        return not self.reasons


@dataclass
class CompileResult:
    """Lo que devuelve `compile`: aceptados (escritos o no), rechazados con razones, y el gasto."""

    kb_id: str
    request: str
    model: str
    proposals: list[dict[str, Any]]
    rejected: list[dict[str, Any]]
    usage: dict[str, Any] | None
    written: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------------------------
# Índice de fragmentos
# --------------------------------------------------------------------------------------------


@dataclass
class ChunkIndex:
    embedder_id: str
    content_hash: str
    ids: list[str]
    vectors: list[list[float]]
    chunks: dict[str, dict[str, Any]]
    cached: bool = False

    def __len__(self) -> int:
        return len(self.ids)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def _chunk_row(document: Any) -> dict[str, Any]:
    payload = document.payload
    return {"chunk_id": document.name, "source": payload.get("source"), "index": payload.get("index"), "page": payload.get("page"), "text": str(payload.get("text") or "")}


def chunk_index(kb_id: str, root: Path | str | None = None, *, embedder: Any | None = None, writer: KbWriter | None = None) -> ChunkIndex:
    """Los `SourceChunk` de la KB embebidos con `embedder` (HashEmbedder por defecto), cacheados en
    `<kb>/.cache/chunks-<embedder>.json` e invalidados por el hash de contenido de los fragmentos."""
    writer = writer or KbWriter.open(kb_id, root)
    embedder = embedder or HashEmbedder()
    kb = writer.kb()
    documents = sorted(kb.by_model("SourceChunk"), key=lambda d: d.name) if "SourceChunk" in writer.registered_models() else []
    digest = hashlib.sha256("\n".join(f"{d.name}\t{d.content_hash}" for d in documents).encode("utf-8")).hexdigest()
    chunks = {d.name: _chunk_row(d) for d in documents}
    ids = [d.name for d in documents]
    cache = writer.root / CACHE_DIR / f"chunks-{re.sub(r'[^a-z0-9]+', '-', embedder.id().lower())}.json"
    if cache.is_file():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("content_hash") == digest and data.get("embedder_id") == embedder.id() and data.get("ids") == ids:
                return ChunkIndex(embedder.id(), digest, ids, data["vectors"], chunks, cached=True)
        except (ValueError, KeyError, TypeError):
            log.warning("caché de fragmentos ilegible, se regenera: %s", cache)
    vectors = embedder.embed([chunks[i]["text"] for i in ids]) if ids else []
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"embedder_id": embedder.id(), "content_hash": digest, "ids": ids, "vectors": vectors}), encoding="utf-8")
    return ChunkIndex(embedder.id(), digest, ids, vectors, chunks)


def search_index(index: ChunkIndex, query: str, k: int = 5, *, embedder: Any | None = None) -> list[dict[str, Any]]:
    """Los `k` fragmentos más parecidos a `query`: `[{chunk_id, source, index, page, score, text}]`."""
    if not index.ids:
        return []
    embedder = embedder or HashEmbedder()
    vector = embedder.embed([query])[0]
    scored = sorted(((_cosine(vector, v), i) for i, v in zip(index.ids, index.vectors, strict=False)), key=lambda s: (-s[0], s[1]))
    return [{**index.chunks[chunk_id], "score": round(score, 4)} for score, chunk_id in scored[: max(1, k)]]


def search_chunks(kb_id: str, query: str, k: int = 5, root: Path | str | None = None) -> list[dict[str, Any]]:
    """`search_index` sobre el índice (cacheado) de la KB."""
    return search_index(chunk_index(kb_id, root), query, k)


# --------------------------------------------------------------------------------------------
# Similitud con átomos existentes y respaldo (Jev)
# --------------------------------------------------------------------------------------------


def atom_vectors(kb: Any, embedder: Any) -> tuple[list[str], list[list[float]]]:
    """Título + respuesta de cada `KnowledgeAtom`, embebidos con `embedder`."""
    atoms = kb.by_model(world.KNOWLEDGE_MODEL)
    ids = [d.name for d in atoms]
    texts = [f"{d.payload.get('title') or d.name}. {d.payload.get('answer') or ''}" for d in atoms]
    return ids, (embedder.embed(texts) if texts else [])


def similar_atoms(text: str, vectors: tuple[list[str], list[list[float]]], embedder: Any, k: int = 3) -> list[tuple[str, float]]:
    """Los `k` átomos existentes más parecidos a `text` (coseno), de mayor a menor."""
    ids, matrix = vectors
    if not ids:
        return []
    vector = embedder.embed([text])[0]
    scored = sorted(((round(_cosine(vector, v), 4), i) for i, v in zip(ids, matrix, strict=False)), key=lambda s: (-s[0], s[1]))
    return [(i, s) for s, i in scored[:k]]


def grounded_noul(client: Any, answer: str, fragment: str, *, model: str | None = None) -> float | None:
    """Noul de Jev: ¿`answer` está respaldada por `fragment`? None si no hay cliente o falló."""
    from tutor.selector_jev import DEFAULT_MODEL, make_noul

    if client is None:
        return None
    try:
        response = client.system_one(
            state={"atom_answer": answer, "cited_fragment": fragment[:6000]},
            questions={GROUNDED_NAME: make_noul(GROUNDED_INSTRUCTIONS, GROUNDED_CRITERIA)},
            model=model or DEFAULT_MODEL,
        )
        return float(response.answers[GROUNDED_NAME].noul)
    except Exception as error:  # red, cuota, auth: el respaldo queda sin evaluar
        log.warning("Jev no pudo evaluar el respaldo (%s): %s", type(error).__name__, error)
        return None


# --------------------------------------------------------------------------------------------
# Tools del agente
# --------------------------------------------------------------------------------------------


class CompilerTools:
    """Lectura de la KB para el modelo: fragmentos, átomos, ramas. Devuelven texto plano."""

    def __init__(self, kb: Any, index: ChunkIndex, embedder: Any) -> None:
        self.kb = kb
        self.index = index
        self.embedder = embedder
        self.calls: list[tuple[str, str]] = []

    def search_chunks(self, query: str, k: int = 5) -> str:
        """Busca en los fragmentos de las fuentes ingeridas (en inglés, el idioma de la fuente) los `k`
        más parecidos a `query`. Una entrada por fragmento: chunk_id · página · puntaje · inicio del texto.
        Lee el fragmento completo con get_chunk antes de citarlo."""
        self.calls.append(("search_chunks", query))
        rows = search_index(self.index, query, k, embedder=self.embedder)
        return "\n\n".join(f"{r['chunk_id']} · p. {r['page'] or '?'} · {r['score']:.2f}\n{r['text'][:500]}" for r in rows) or "sin fragmentos"

    def get_chunk(self, chunk_id: str) -> str:
        """El texto completo de un fragmento por su chunk_id, con fuente y página."""
        self.calls.append(("get_chunk", chunk_id))
        row = self.index.chunks.get(chunk_id.strip().strip("`"))
        if row is None:
            return f"no existe el fragmento {chunk_id!r}; usa un chunk_id devuelto por search_chunks"
        return f"{row['chunk_id']} · fuente {row['source']} · p. {row['page'] or '?'}\n\n{row['text']}"

    def search_atoms(self, query: str, k: int = 5) -> str:
        """Los `k` átomos que YA existen en la KB más parecidos a `query` (id · título · puntaje · respuesta
        recortada). Úsalo antes de proponer para no repetir lo que la KB ya afirma."""
        self.calls.append(("search_atoms", query))
        lines = []
        for atom_id, score in world.rank(self.kb, query, k):
            atom = world.get_atom(self.kb, atom_id) or {}
            lines.append(f"{atom_id} · {atom.get('title')} · {score:.2f}\n  {str(atom.get('summary') or '')[:300]}")
        return "\n".join(lines) or "sin átomos"

    def get_atom(self, atom_id: str) -> str:
        """Un átomo o rama existente completo por id: título, pregunta, respuesta, tags, procedencia, parent."""
        self.calls.append(("get_atom", atom_id))
        atom = world.get_atom(self.kb, atom_id.strip().strip("`[]"))
        if atom is None:
            return f"no existe {atom_id!r}"
        return "\n".join(f"{key}: {atom.get(key)}" for key in ("id", "model", "title", "question", "summary", "tags", "parent", "provenance"))

    def list_branches(self) -> str:
        """Todas las ramas de la taxonomía (id · título · parent): el `parent` de una propuesta debe ser una de ellas."""
        self.calls.append(("list_branches", ""))
        return "\n".join(f"{b['id']} · {b['title']} · parent={b.get('parent')}" for b in world.list_branches(self.kb))


def render_examples(kb: Any, request: str, n: int = 3) -> str:
    """`n` átomos existentes (los más cercanos a la petición) como muestra de voz y formato."""
    ids = [atom_id for atom_id, _ in world.rank(kb, request, n)]
    if len(ids) < n:
        ids += [d.name for d in kb.by_model(world.KNOWLEDGE_MODEL) if d.name not in ids][: n - len(ids)]
    blocks = []
    for atom_id in ids:
        atom = world.get_atom(kb, atom_id) or {}
        blocks.append(
            f"- id: {atom_id}\n  title: {atom.get('title')}\n  question: {atom.get('question')}\n"
            f"  answer: {str(atom.get('summary') or '').strip()}\n  tags: {', '.join(atom.get('tags') or [])}\n  parent: {atom.get('parent')}"
        )
    return "\n".join(blocks) or "(la KB todavía no tiene átomos)"


def instructions_for(kb: Any, kb_id: str, request: str, max_atoms: int) -> str:
    title = str((world.agent(kb) or {}).get("title") or kb.name)
    namespaces = sorted(str(d.payload.get("tag")) for d in kb.by_model("TagNamespaceDoc"))
    branches = "\n".join(f"- {b['id']} · {b['title']}" for b in world.list_branches(kb))
    return f"""\
Eres el compilador de la base de conocimiento «{title}» (`{kb_id}`): conviertes fragmentos de la fuente \
ingerida en átomos de conocimiento NUEVOS que la KB todavía no afirma.

Un átomo = UNA afirmación atómica, en español, citable, con la misma voz y granularidad que los ejemplos:
- `title`: la afirmación en corto (≤ {TITLE_MAX} caracteres).
- `question`: la pregunta 5W1H que responde (what, why, how, how_not, when, where, for_whom).
- `answer`: una sola afirmación (≤ {ANSWER_MAX_WORDS} palabras), fiel al fragmento, sin encabezados ni listas.
- `provenance`: `chunk_ids` reales (los que leíste con get_chunk), `quote` = cita textual corta copiada \
del fragmento en su idioma original, `where` = página o sección.
- `tags`: `system:{kb_id}` siempre; `topic:<concepto>` en el estilo de los existentes; `layer:theory`, \
`layer:pedagogy` o `layer:example`; `domain:mathematics-education`. Namespaces declarados: {', '.join(namespaces)}.
- `parent`: el id de UNA rama existente de la lista de abajo (nunca un átomo ni una rama inventada).
- `rationale`: qué pregunta o vacío cubre que la KB no cubría.

Método, en este orden:
1. Busca fragmentos con `search_chunks` (varias consultas, EN INGLÉS: la fuente está en inglés).
2. Lee completos con `get_chunk` los fragmentos que vas a citar.
3. Comprueba con `search_atoms` que la KB no tenga ya un átomo que diga lo mismo; si lo tiene, no lo repitas.
4. Propón como máximo {max_atoms} átomos; menos si la fuente no respalda más. No inventes: todo lo que \
afirme `answer` debe estar en el fragmento citado.

Ramas disponibles (`parent`):
{branches}

Ejemplos de átomos existentes (misma voz):
{render_examples(kb, request)}
"""


def build_compiler_agent(kb: Any, kb_id: str, request: str, *, model: Any, tools: CompilerTools, max_atoms: int) -> Any:
    from pydantic_ai import Agent

    return Agent(
        model,
        deps_type=type(None),
        output_type=list[AtomProposal],
        instructions=instructions_for(kb, kb_id, request, max_atoms),
        tools=[tools.search_chunks, tools.get_chunk, tools.search_atoms, tools.get_atom, tools.list_branches],
        retries=2,
    )


# --------------------------------------------------------------------------------------------
# Revisión en código y escritura
# --------------------------------------------------------------------------------------------


def review(
    writer: KbWriter,
    proposal: AtomProposal,
    *,
    embedder: Any,
    vectors: tuple[list[str], list[list[float]]],
    index: ChunkIndex,
    jev_client: Any | None = None,
    taken: set[str] | None = None,
) -> Review:
    """Rechaza (con razones) si el parent no es una rama existente, si la procedencia no cita fragmentos
    reales, si duplica un átomo existente (coseno > {DUPLICATE_THRESHOLD}) o repite un id de la tanda;
    anota `similar_to` y, si hay Jev, `grounded`."""
    kb_id = writer.kb_id
    try:
        atom_id = slugify(proposal.title, "atom-")
    except AuthoringError as error:
        atom_id = "atom-sin-id"
        return Review(atom_id, proposal, [error.message])
    verdict = Review(atom_id, proposal)
    parent = writer.find(proposal.parent)
    if parent is None:
        verdict.reasons.append(f"parent {proposal.parent!r} no existe")
    elif parent.model != world.BRANCH_MODEL:
        verdict.reasons.append(f"parent {proposal.parent!r} es {parent.model}, no una rama")
    missing = [c for c in proposal.provenance.chunk_ids if c not in index.chunks]
    if missing:
        verdict.reasons.append(f"provenance cita fragmentos inexistentes: {missing}")
    existing = writer.find(atom_id)
    if existing is not None and existing.model != MODEL:
        verdict.reasons.append(f"ya existe {existing.model} con id {atom_id!r}")
    if taken is not None and atom_id in taken:
        verdict.reasons.append(f"id {atom_id!r} repetido en la tanda")
    verdict.similar_to = [(i, s) for i, s in similar_atoms(f"{proposal.title}. {proposal.answer}", vectors, embedder) if s >= SIMILAR_THRESHOLD]
    if verdict.similar_to and verdict.similar_to[0][1] > DUPLICATE_THRESHOLD:
        best, score = verdict.similar_to[0]
        verdict.reasons.append(f"duplicado de {best} (similitud {score:.2f} > {DUPLICATE_THRESHOLD})")
    if f"system:{kb_id}" not in proposal.tags:
        proposal.tags.append(f"system:{kb_id}")
    if not missing and verdict.accepted:
        fragment = "\n\n".join(index.chunks[c]["text"] for c in proposal.provenance.chunk_ids)
        verdict.grounded_noul = grounded_noul(jev_client, proposal.answer, fragment)
        verdict.grounded = None if verdict.grounded_noul is None else verdict.grounded_noul >= GROUNDED_THRESHOLD
    return verdict


def provenance_text(index: ChunkIndex, kb: Any, provenance: Provenance) -> str:
    """La procedencia como texto citable: fuente, página, fragmentos y cita."""
    rows = [index.chunks[c] for c in provenance.chunk_ids if c in index.chunks]
    sources = []
    for source_id in dict.fromkeys(r["source"] for r in rows):
        doc = world.get_atom(kb, str(source_id))
        sources.append(str((doc or {}).get("title") or source_id))
    pages = sorted({int(r["page"]) for r in rows if r.get("page")})
    where = provenance.where.strip() or (f"p. {', '.join(map(str, pages))}" if pages else "")
    parts = [f"Fuente: {'; '.join(sources) or 'fragmentos ingeridos'}" + (f" ({where})" if where else "") + "."]
    parts.append("Fragmentos: " + ", ".join(f"`{c}`" for c in provenance.chunk_ids) + ".")
    parts.append(f"Cita: «{provenance.quote}».")
    return " ".join(parts)


def structured_provenance(index: ChunkIndex, provenance: Provenance, *, note: str | None = None, grounded_noul: float | None = None) -> list[dict[str, Any]]:
    """La procedencia del propuesto como `kb_models.provenance.Provenance` (para el `KnowledgeAtom` al aprobar):
    fuente y páginas reales de los fragmentos citados, la cita como `excerpt`, el noul de Jev si lo hubo."""
    from kb_models.provenance import Provenance as KbProvenance
    from kb_models.provenance import ProvenanceKind

    rows = [index.chunks[c] for c in provenance.chunk_ids if c in index.chunks]
    pages = sorted({int(r["page"]) for r in rows if r.get("page")})
    source = str(rows[0]["source"]) if rows else None
    where = provenance.where.strip()
    extra = ", ".join(p for p in (where, note) if p) or None
    item = KbProvenance(
        kind=ProvenanceKind.BOOK if rows else ProvenanceKind.DERIVED,
        source=source,
        pages=[pages[0], pages[-1]] if pages else None,
        excerpt=provenance.quote,
        chunk_ids=[r["chunk_id"] for r in rows],
        nouls=[grounded_noul] * len(rows) if grounded_noul is not None else [],
        anchored=(grounded_noul >= GROUNDED_THRESHOLD) if grounded_noul is not None else None,
        note=extra,
    )
    return [item.model_dump(mode="json")]


def proposed_payload(kb_id: str, verdict: Review, *, request: str, model: str, provenance: str) -> dict[str, Any]:
    p = verdict.proposal
    return {
        "id": verdict.id,
        "title": p.title,
        "five_wh_one_plus": p.question,
        "tags": list(dict.fromkeys(p.tags)),
        "parent": p.parent,
        "status": "proposed",
        "request": request,
        "created_by": model,
        "chunk_ids": list(p.provenance.chunk_ids),
        "similar_to": [f"{i}:{s:.2f}" for i, s in verdict.similar_to],
        "grounded": verdict.grounded,
        "rejected_why": None,
        "answer": demote_headings(p.answer),
        "provenance": demote_headings(provenance),
        "rationale": demote_headings(p.rationale),
    }


def _proposal_dict(doc_name: str, payload: dict[str, Any], path: str | None = None) -> dict[str, Any]:
    return {
        "id": doc_name,
        "title": payload.get("title"),
        "question": payload.get("five_wh_one_plus"),
        "answer": payload.get("answer"),
        "provenance": payload.get("provenance"),
        "tags": list(payload.get("tags") or []),
        "parent": payload.get("parent"),
        "rationale": payload.get("rationale"),
        "status": payload.get("status"),
        "request": payload.get("request"),
        "created_by": payload.get("created_by"),
        "chunk_ids": list(payload.get("chunk_ids") or []),
        "similar_to": list(payload.get("similar_to") or []),
        "grounded": payload.get("grounded"),
        "rejected_why": payload.get("rejected_why"),
        "path": path,
    }


def default_model_name() -> str:
    return os.environ.get(ENV_MODEL) or "test"


def compile_max_tokens() -> int:
    from tutor.agent import max_output_tokens

    try:
        return max(256, int(os.environ.get(ENV_MAX_TOKENS) or max_output_tokens()))
    except ValueError:
        log.warning("%s inválido; uso el tope del tutor", ENV_MAX_TOKENS)
        return max_output_tokens()


def compile(  # noqa: A001 — es el verbo del dominio
    kb_id: str,
    request: str,
    *,
    model: str | None = None,
    max_atoms: int = 5,
    write: bool = True,
    root: Path | str | None = None,
    agent_model: Any | None = None,
    jev_client: Any | None = None,
    embedder: Any | None = None,
) -> CompileResult:
    """Pide al modelo hasta `max_atoms` átomos para `request`, los revisa en código y, con `write`,
    escribe los aceptados como `ProposedAtom`. `agent_model` (un `Model` de pydantic-ai) reemplaza al
    de `model`/`TUTOR_MODEL` (para tests); `jev_client=None` usa Jev si hay `TYPESAFE_API_KEY`."""
    from agents.run import usage_of
    from pydantic_ai.usage import UsageLimits

    from tutor.agent import resolve_model
    from tutor.selector_jev import default_client

    request = " ".join(str(request).split())
    if not request:
        raise AuthoringError("la petición está vacía", "pasa un tema o una pregunta de estudiante")
    max_atoms = max(1, min(int(max_atoms), 20))
    writer = KbWriter.open(kb_id, root)
    kb = writer.kb()
    embedder = embedder or HashEmbedder()
    index = chunk_index(kb_id, root, embedder=embedder, writer=writer)
    if not index.ids:
        raise AuthoringError(f"la KB {kb_id!r} no tiene fragmentos ingeridos", "ingiere una fuente con `tutor compile ingest <archivo>` o ingest_pdf")
    model_name = model or default_model_name()
    resolved = agent_model if agent_model is not None else resolve_model(model_name)
    label = model_name if agent_model is None else f"{getattr(resolved, 'system', 'local')}:{getattr(resolved, 'model_name', 'model')}"
    tools = CompilerTools(kb, index, embedder)
    agent = build_compiler_agent(kb, kb_id, request, model=resolved, tools=tools, max_atoms=max_atoms)
    run = agent.run_sync(
        f"Petición: {request}\n\nPropón hasta {max_atoms} átomos nuevos que la respalden en la fuente.",
        usage_limits=UsageLimits(request_limit=MAX_REQUESTS),
        model_settings={"max_tokens": compile_max_tokens()},
    )
    proposals: list[AtomProposal] = list(run.output)[:max_atoms]
    client = jev_client if jev_client is not None else default_client()
    vectors = atom_vectors(kb, embedder)
    taken: set[str] = set()
    accepted: list[tuple[Review, dict[str, Any]]] = []
    rejected: list[dict[str, Any]] = []
    for proposal in proposals:
        verdict = review(writer, proposal, embedder=embedder, vectors=vectors, index=index, jev_client=client, taken=taken)
        if not verdict.accepted:
            rejected.append({"id": verdict.id, "title": proposal.title, "answer": proposal.answer, "reasons": verdict.reasons, "similar_to": [f"{i}:{s:.2f}" for i, s in verdict.similar_to]})
            continue
        taken.add(verdict.id)
        payload = proposed_payload(kb_id, verdict, request=request, model=label, provenance=provenance_text(index, kb, proposal.provenance))
        accepted.append((verdict, payload))
    if write and accepted:
        docs = [kb_build.Doc(MODEL, f"{FOLDERS[MODEL]}/{payload['id']}.md", payload, name=payload["id"]) for _, payload in accepted]
        for _, payload in accepted:
            authoring._ensure_namespaces(writer, payload["tags"], payload["id"])
        writer.write_many(docs)
        writer.refresh(index=False)
    out = [_proposal_dict(payload["id"], payload, f"{FOLDERS[MODEL]}/{payload['id']}.md" if write else None) for _, payload in accepted]
    for (verdict, _), item in zip(accepted, out, strict=False):
        item["grounded_noul"] = verdict.grounded_noul
    log.info("compile %s: %d propuestos, %d rechazados (%s)", kb_id, len(out), len(rejected), label)
    return CompileResult(kb_id, request, label, out, rejected, usage_of(run).model_dump(), write and bool(accepted))


# --------------------------------------------------------------------------------------------
# Propuestos: listar, ver, aprobar, rechazar
# --------------------------------------------------------------------------------------------


def _proposed_docs(writer: KbWriter) -> list[Any]:
    if MODEL not in writer.registered_models():
        return []
    return writer.kb().by_model(MODEL)


def list_proposed(kb_id: str, status: str = "proposed", root: Path | str | None = None) -> list[dict[str, Any]]:
    """Los propuestos con ese `status` (`proposed`, `rejected`, `all`); `approved` lista los
    `KnowledgeAtom` que vienen del compilador (su procedencia lleva la marca)."""
    writer = KbWriter.open(kb_id, root)
    if status not in (*STATUSES, "all"):
        raise AuthoringError(f"status inválido: {status!r}", "usa proposed, approved, rejected o all")
    if status == "approved":
        return [
            {**_proposal_dict(d.name, d.payload, d.path), "status": "approved"}
            for d in writer.kb().by_model(world.KNOWLEDGE_MODEL)
            if COMPILER_MARK in " ".join(str(p.get("note") or "") for p in (d.payload.get("provenance") or []) if isinstance(p, dict))
        ]
    return [_proposal_dict(d.name, d.payload, d.path) for d in _proposed_docs(writer) if status == "all" or d.payload.get("status") == status]


def get_proposed(kb_id: str, atom_id: str, root: Path | str | None = None) -> dict[str, Any]:
    """Un propuesto completo, con su markdown."""
    writer = KbWriter.open(kb_id, root)
    document = writer.require(atom_id, "átomo propuesto")
    if document.model != MODEL:
        raise AuthoringError(f"{atom_id!r} es {document.model}, no un propuesto", "usa list_proposed")
    return {**_proposal_dict(document.name, document.payload, document.path), "markdown": writer.kb().render(document.key)}


def approve(kb_id: str, atom_id: str, root: Path | str | None = None) -> dict[str, Any]:
    """Convierte el propuesto en `KnowledgeAtom` con el mismo id (borra `proposed/<id>.md`, escribe
    `knowledge/<id>.md` y su `child_of` vía `upsert_atom`). Desde ese momento el tutor lo ve."""
    writer = KbWriter.open(kb_id, root)
    document = writer.require(atom_id, "átomo propuesto")
    if document.model != MODEL:
        raise AuthoringError(f"{atom_id!r} es {document.model}, no un propuesto", "solo se aprueban ProposedAtom")
    payload = dict(document.payload)
    parent = writer.require(str(payload.get("parent") or ""), "parent (rama)")
    if parent.model != world.BRANCH_MODEL:
        raise AuthoringError(f"el parent {parent.name!r} es {parent.model}, no una rama", "corrige el parent con upsert_branch/list_branches")
    note = f"Compilado por {COMPILER_MARK} ({payload.get('created_by')}) a pedido de «{payload.get('request')}»; aprobado"
    index = chunk_index(kb_id, root, writer=writer)
    quote = re.search(r"Cita: «(.+?)»", str(payload.get("provenance") or ""), re.S)
    cited = Provenance(chunk_ids=list(payload.get("chunk_ids") or []) or ["sin-chunk-0"], quote=(quote.group(1) if quote else str(payload.get("provenance") or "")[:200]) or "-")
    atom = {
        "id": document.name,
        "title": payload.get("title"),
        "question": payload.get("five_wh_one_plus"),
        "answer": payload.get("answer"),
        "provenance": structured_provenance(index, cited, note=note, grounded_noul=None if payload.get("grounded") is None else (1.0 if payload.get("grounded") else 0.0)),
        "tags": list(payload.get("tags") or []),
        "parent": parent.name,
    }
    if not atom["provenance"][0]["chunk_ids"]:
        atom["provenance"][0]["note"] = f"{str(payload.get('provenance') or '').strip()} {note}".strip()
    writer.delete(document.name)
    try:
        result = authoring.upsert_atom(kb_id, atom, root)
    except Exception:
        # No perder la propuesta si el átomo no se pudo escribir: se restaura tal cual estaba.
        writer.write(kb_build.Doc(MODEL, document.path, payload, name=document.name))
        writer.refresh(index=False)
        raise
    return {**result, "approved": document.name, "rationale": payload.get("rationale"), "grounded": payload.get("grounded")}


def reject(kb_id: str, atom_id: str, why: str = "", root: Path | str | None = None) -> dict[str, Any]:
    """Marca el propuesto como `rejected` (queda en `proposed/` con el motivo, para no volver a proponerlo)."""
    writer = KbWriter.open(kb_id, root)
    document = writer.require(atom_id, "átomo propuesto")
    if document.model != MODEL:
        raise AuthoringError(f"{atom_id!r} es {document.model}, no un propuesto", "solo se rechazan ProposedAtom")
    payload = {**document.payload, "status": "rejected", "rejected_why": " ".join(str(why).split()) or None}
    writer.write(kb_build.Doc(MODEL, document.path, payload, name=document.name))
    writer.refresh(index=False)
    return _proposal_dict(document.name, payload, document.path)


# --------------------------------------------------------------------------------------------
# Fuentes y vacíos
# --------------------------------------------------------------------------------------------


def ingest_source(kb_id: str, path: str | Path, *, title: str | None = None, chunk_chars: int = ingest.DEFAULT_CHUNK_CHARS, root: Path | str | None = None) -> dict[str, Any]:
    """`ingest.ingest_file` (PDF con página por fragmento) y el índice de fragmentos ya calentado."""
    result = ingest.ingest_file(kb_id, path, title=title, chunk_chars=chunk_chars, root=root)
    index = chunk_index(kb_id, root)
    summary = {k: v for k, v in result.items() if k != "chunks"}
    pages = sorted({c["page"] for c in result["chunks"] if c.get("page")})
    return {**summary, "pages": (pages[0], pages[-1]) if pages else None, "index_size": len(index), "index_cached": index.cached}


def load_questions(path: str | Path) -> list[str]:
    """Preguntas desde un YAML (`questions: [{question}]` o lista de strings) o un texto (una por línea)."""
    file = Path(path).expanduser()
    if not file.is_file():
        raise AuthoringError(f"no existe {file}", "pasa un .yaml con `questions:` o un .txt con una pregunta por línea")
    text = file.read_text(encoding="utf-8")
    if file.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(text) or {}
        items = data.get("questions") if isinstance(data, dict) else data
        return [str(q.get("question") if isinstance(q, dict) else q).strip() for q in items or [] if q]
    return [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]


def gaps(
    kb_id: str,
    questions: list[str],
    *,
    root: Path | str | None = None,
    client: Any | None = None,
    threshold: float = GAP_THRESHOLD,
    pool: int = GAP_POOL,
    role: str = "tutor",
) -> dict[str, Any]:
    """Para cada pregunta, el noul máximo de la mesa (`JevSelector.score` sobre el top-`pool` por
    embedding dentro de la proyección del rol); `gap` si queda bajo `threshold`. Sin Jev (sin key o sin
    `client`) devuelve `gap: None` y `jev: false`."""
    from tutor.agent import SELECTOR_TEXT_CHARS
    from tutor.selector_jev import JevSelector

    questions = [" ".join(str(q).split()) for q in questions if str(q).strip()]
    if not questions:
        raise AuthoringError("no hay preguntas", "pasa al menos una")
    writer = KbWriter.open(kb_id, root)
    kb = writer.kb()
    projection = str((world.agent(kb, role) or {}).get("projection") or role)
    visible = {d.key: d for d in kb.in_projection(projection) if d.is_a(world.KNOWLEDGE_MODEL)}
    selector = JevSelector(client=client, k=pool)
    rows: list[dict[str, Any]] = []
    jev_ok = True
    for question in questions:
        hits = kb.rank(question, k=pool, among=list(visible)) if visible else []
        candidates = [(h.name, f"{h.document.payload.get('title') or h.name}. {str(h.document.payload.get('answer') or '')[:SELECTOR_TEXT_CHARS]}") for h in hits]
        scored = selector.score(question, candidates, role=role) if candidates else []
        if scored is None:
            jev_ok = False
            rows.append({"question": question, "max_noul": None, "best_atom": hits[0].name if hits else None, "gap": None, "top": []})
            continue
        best, noul = scored[0] if scored else (None, 0.0)
        rows.append({"question": question, "max_noul": round(float(noul), 3), "best_atom": best, "gap": float(noul) < threshold, "top": [(i, round(float(p), 3)) for i, p in scored[:3]]})
    gap_questions = [r["question"] for r in rows if r["gap"]]
    return {"kb_id": kb_id, "threshold": threshold, "jev": jev_ok, "n_questions": len(rows), "n_gaps": len(gap_questions), "gaps": gap_questions, "rows": rows}


# --------------------------------------------------------------------------------------------
# CLI: `tutor compile …`
# --------------------------------------------------------------------------------------------


def _resolve_kb(value: str | None) -> tuple[str, Path | None]:
    """`--kb` acepta un id (bajo TUTOR_KBS_ROOT o kbs/) o la ruta de la KB; sin valor, TUTOR_KB o kbs/apos."""
    if value is None:
        path = world.kb_root_default()
        return path.name, path.parent
    candidate = Path(value).expanduser()
    if (candidate / "kb.yaml").is_file():
        resolved = candidate.resolve()
        return resolved.name, resolved.parent
    return value, None


def register_cli(app: Any) -> None:
    """Agrega el sub-typer `compile` a la CLI `tutor`."""
    import typer

    cli = typer.Typer(help="Compilar átomos nuevos desde las fuentes ingeridas; revisar, aprobar y rechazar propuestos.", no_args_is_help=True)
    KbOpt = typer.Option(None, "--kb", help="Id de la KB (bajo TUTOR_KBS_ROOT o kbs/) o su ruta; por defecto TUTOR_KB o kbs/apos.")

    def fail(error: AuthoringError) -> None:
        typer.echo(f"error: {error.message}" + (f" ({error.hint})" if error.hint else ""), err=True)
        raise typer.Exit(1)

    @cli.command("run")
    def run(
        request: str = typer.Argument(help="Tema o pregunta de estudiante que la KB no cubre."),
        kb: str | None = KbOpt,
        max_atoms: int = typer.Option(5, "--max", help="Máximo de átomos a proponer."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Proponer y revisar sin escribir nada."),
        model: str | None = typer.Option(None, "--model", help="provider:model; por defecto TUTOR_MODEL."),
        as_json: bool = typer.Option(False, "--json", help="Volcar el CompileResult como JSON."),
    ) -> None:
        """Pide átomos al modelo, los revisa y escribe los aceptados como propuestos."""
        kb_id, root = _resolve_kb(kb)
        try:
            result = compile(kb_id, request, model=model, max_atoms=max_atoms, write=not dry_run, root=root)
        except AuthoringError as error:
            fail(error)
            return
        except Exception as error:  # noqa: BLE001 — el modelo falló (red, crédito, salida inválida): una línea, no un traceback
            typer.echo(f"error del modelo ({type(error).__name__}): {str(error).strip().splitlines()[0][:300] if str(error).strip() else '-'}", err=True)
            raise typer.Exit(2) from error
        if as_json:
            typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            return
        typer.echo(f"compile · {kb_id} · {result.model} · {len(result.proposals)} propuestos, {len(result.rejected)} rechazados" + (" (dry-run)" if dry_run else ""))
        for item in result.proposals:
            typer.echo(render_proposal(item))
        for item in result.rejected:
            typer.echo(f"\n✗ {item['title']}\n  rechazado: {'; '.join(item['reasons'])}" + (f"\n  similar_to: {', '.join(item['similar_to'])}" if item.get("similar_to") else ""))
        if result.usage:
            typer.echo(f"\nuso: {result.usage}")

    @cli.command("list")
    def list_cmd(kb: str | None = KbOpt, status: str = typer.Option("proposed", "--status", help="proposed | approved | rejected | all.")) -> None:
        """Los propuestos (o aprobados) de la KB."""
        kb_id, root = _resolve_kb(kb)
        try:
            items = list_proposed(kb_id, status, root)
        except AuthoringError as error:
            fail(error)
            return
        if not items:
            typer.echo(f"sin átomos con status {status}")
            return
        width = max(len(i["id"]) for i in items)
        for item in items:
            grounded = {True: "grounded", False: "NO-grounded", None: "sin-jev"}[item.get("grounded")]
            typer.echo(f"{item['id'].ljust(width)}  {item['status']:<9} {grounded:<12} {item['title']}")

    @cli.command("show")
    def show(atom_id: str = typer.Argument(help="Id del propuesto."), kb: str | None = KbOpt) -> None:
        """Un propuesto completo."""
        kb_id, root = _resolve_kb(kb)
        try:
            item = get_proposed(kb_id, atom_id, root)
        except AuthoringError as error:
            fail(error)
            return
        typer.echo(render_proposal(item))
        typer.echo(f"  request: {item['request']}\n  created_by: {item['created_by']}\n  rationale: {item['rationale']}")
        if item.get("rejected_why"):
            typer.echo(f"  rejected_why: {item['rejected_why']}")

    @cli.command("approve")
    def approve_cmd(atom_ids: list[str] = typer.Argument(help="Ids de propuestos."), kb: str | None = KbOpt) -> None:
        """Convierte propuestos en átomos de conocimiento (el tutor los ve desde ya)."""
        kb_id, root = _resolve_kb(kb)
        for atom_id in atom_ids:
            try:
                result = approve(kb_id, atom_id, root)
            except AuthoringError as error:
                fail(error)
                return
            typer.echo(f"aprobado {result['approved']} → KnowledgeAtom bajo {result.get('parent')}")

    @cli.command("reject")
    def reject_cmd(atom_ids: list[str] = typer.Argument(help="Ids de propuestos."), kb: str | None = KbOpt, why: str = typer.Option("", "--why", help="Motivo.")) -> None:
        """Marca propuestos como rechazados."""
        kb_id, root = _resolve_kb(kb)
        for atom_id in atom_ids:
            try:
                result = reject(kb_id, atom_id, why, root)
            except AuthoringError as error:
                fail(error)
                return
            typer.echo(f"rechazado {result['id']}" + (f": {why}" if why else ""))

    @cli.command("ingest")
    def ingest_cmd(
        path: Path = typer.Argument(help="Archivo .pdf, .md o .txt."),
        kb: str | None = KbOpt,
        title: str | None = typer.Option(None, "--title", help="Título de la fuente (deriva el source_id)."),
        chunk_chars: int = typer.Option(ingest.DEFAULT_CHUNK_CHARS, "--chunk-chars"),
    ) -> None:
        """Ingiere una fuente (fragmentos con página si es PDF) y calienta el índice de fragmentos."""
        kb_id, root = _resolve_kb(kb)
        try:
            result = ingest_source(kb_id, path, title=title, chunk_chars=chunk_chars, root=root)
        except AuthoringError as error:
            fail(error)
            return
        typer.echo(f"{result['source_id']}: {result['n_chunks']} fragmentos (páginas {result['pages']}), índice de {result['index_size']}" + (" (reemplazó la fuente anterior)" if result.get("replaced") else ""))

    @cli.command("gaps")
    def gaps_cmd(
        questions: Path = typer.Option(..., "--questions", help="YAML con `questions:` (como benchmarks/apos_questions.yaml) o .txt con una por línea."),
        kb: str | None = KbOpt,
        threshold: float = typer.Option(GAP_THRESHOLD, "--threshold"),
        as_json: bool = typer.Option(False, "--json"),
    ) -> None:
        """Qué preguntas no cubre bien la mesa (noul máximo < umbral): candidatas a compilar. Requiere Jev."""
        kb_id, root = _resolve_kb(kb)
        try:
            result = gaps(kb_id, load_questions(questions), root=root, threshold=threshold)
        except AuthoringError as error:
            fail(error)
            return
        if as_json:
            typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if not result["jev"]:
            typer.echo("Jev no disponible (TYPESAFE_API_KEY / typesafe-sdk): no se puede medir cobertura", err=True)
        for row in result["rows"]:
            mark = "GAP " if row["gap"] else ("ok  " if row["gap"] is False else "?   ")
            noul = f"{row['max_noul']:.2f}" if row["max_noul"] is not None else "  - "
            typer.echo(f"{mark} {noul}  {row['question'][:90]}  ← {row['best_atom']}")
        typer.echo(f"\n{result['n_gaps']} de {result['n_questions']} preguntas bajo {threshold}")

    @cli.command("branches")
    def branches_cmd(
        ids: list[str] | None = typer.Argument(None, help="Ids de ramas a describir (vacío con --all = todas)."),
        kb: str | None = KbOpt,
        all_branches: bool = typer.Option(False, "--all", help="Todas las ramas de la KB."),
        model: str = typer.Option(None, "--model", help="provider:model; por defecto google-gla:gemini-2.5-flash."),
        desk: Path = typer.Option(Path("desk/atoms/branches"), "--desk", help="Carpeta de las ramas fuente."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Mostrar las descripciones sin escribir."),
    ) -> None:
        """Regenera la descripción de ramas con el modelo (2–3 oraciones, en español, desde títulos y respuestas
        de sus hijos) y la escribe en la fuente de verdad `desk/atoms/branches/<id>.md`. Luego `tutor kb build`."""
        from tutor import branches as branches_mod

        kb_id, root = _resolve_kb(kb)
        opened = KbWriter.open(kb_id, root).kb()
        wanted = list(ids or [])
        if all_branches:
            wanted = [b["id"] for b in world.list_branches(opened)]
        if not wanted:
            typer.echo("indica ids de ramas o --all", err=True)
            raise typer.Exit(1)
        unknown = [i for i in wanted if (world.get_atom(opened, i) or {}).get("model") != world.BRANCH_MODEL]
        if unknown:
            typer.echo(f"no son ramas: {unknown}", err=True)
            raise typer.Exit(1)
        chosen = model or branches_mod.DEFAULT_MODEL
        try:
            if dry_run:
                for branch_id, text in branches_mod.describe_branches(opened, wanted, model=chosen).items():
                    typer.echo(f"\n{branch_id}\n  {text}")
                return
            written = branches_mod.regenerate(opened, wanted, desk, model=chosen)
        except Exception as error:  # noqa: BLE001 — el modelo falló: una línea
            typer.echo(f"error del modelo ({type(error).__name__}): {str(error).strip().splitlines()[0][:300] if str(error).strip() else '-'}", err=True)
            raise typer.Exit(2) from error
        for branch_id, path in written.items():
            typer.echo(f"{branch_id} → {path}")
        typer.echo(f"{len(written)} ramas descritas con {chosen}; corre `tutor kb build` para regenerar la KB")

    app.add_typer(cli, name="compile")


def render_proposal(item: dict[str, Any]) -> str:
    grounded = {True: "sí", False: "NO", None: "sin evaluar"}[item.get("grounded")]
    lines = [
        f"\n✓ {item['id']} [{item.get('status', 'proposed')}]",
        f"  title: {item['title']}",
        f"  question: {item['question']}",
        f"  answer: {item['answer']}",
        f"  provenance: {item['provenance']}",
        f"  parent: {item['parent']} · tags: {', '.join(item.get('tags') or [])}",
        f"  grounded: {grounded}" + (f" ({item['grounded_noul']:.2f})" if item.get("grounded_noul") is not None else ""),
        f"  similar_to: {', '.join(item.get('similar_to') or []) or '-'}",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------
# MCP: tools del compilador
# --------------------------------------------------------------------------------------------


def register_mcp(server: Any, state: Any, safe: Any, annotations: dict[str, Any]) -> None:
    """Suma las tools del compilador al `MCPServer` de `tutor.mcp_server`."""
    root = state.root

    @server.tool(annotations=annotations["writes"])
    @safe
    def compile_atoms(kb_id: str, request: str, max_atoms: int = 5, dry_run: bool = False, model: str | None = None) -> dict[str, Any]:
        """Pide al modelo (TUTOR_MODEL o `model`) hasta `max_atoms` átomos nuevos para `request` (un tema o una
        pregunta de estudiante), con procedencia en los fragmentos ingeridos; los revisa en código (parent real,
        fragmentos reales, no duplicado) y escribe los aceptados como PROPUESTOS, que el tutor no ve hasta
        `approve_atom`. `dry_run` propone sin escribir. Devuelve `{proposals, rejected[{reasons}], usage}`."""
        if not dry_run:
            state.touched(kb_id)
        return compile(kb_id, request, model=model, max_atoms=max_atoms, write=not dry_run, root=root).to_dict()

    @server.tool(name="list_proposed", annotations=annotations["read_only"])
    @safe
    def list_proposed_tool(kb_id: str, status: str = "proposed") -> dict[str, Any]:
        """Los átomos propuestos por el compilador con ese `status` (proposed | rejected | all), o los ya
        aprobados (`approved`): id, título, respuesta, procedencia, grounded, similar_to, petición de origen."""
        return {"status": status, "atoms": list_proposed(kb_id, status, root)}

    @server.tool(annotations=annotations["writes"])
    @safe
    def approve_atom(kb_id: str, atom_id: str) -> dict[str, Any]:
        """Aprueba un propuesto: lo convierte en `KnowledgeAtom` con el mismo id bajo su rama (`child_of`).
        Desde ese momento entra al índice y a la mesa del tutor."""
        state.touched(kb_id)
        return approve(kb_id, atom_id, root)

    @server.tool(annotations=annotations["writes"])
    @safe
    def reject_atom(kb_id: str, atom_id: str, why: str = "") -> dict[str, Any]:
        """Rechaza un propuesto (queda en `proposed/` con status rejected y el motivo)."""
        state.touched(kb_id)
        return reject(kb_id, atom_id, why, root)

    @server.tool(annotations=annotations["writes"])
    @safe
    def ingest_pdf(kb_id: str, path: str, title: str | None = None, chunk_chars: int = ingest.DEFAULT_CHUNK_CHARS) -> dict[str, Any]:
        """Ingiere un PDF (o .md/.txt) del disco del servidor como fuente: fragmentos de ~`chunk_chars` con su
        página, fuera del índice y de la mesa del tutor, y calienta el índice de fragmentos del compilador."""
        state.touched(kb_id)
        return ingest_source(kb_id, path, title=title, chunk_chars=chunk_chars, root=root)

    @server.tool(annotations=annotations["calls_model"])
    @safe
    def find_gaps(kb_id: str, questions: list[str], threshold: float = GAP_THRESHOLD) -> dict[str, Any]:
        """Para cada pregunta, el noul máximo (Jev) de los 30 átomos más cercanos de la mesa; `gap: true` si
        ninguno la cubre (noul < threshold): candidatas a `compile_atoms`. Sin TYPESAFE_API_KEY, `jev: false`."""
        return gaps(kb_id, questions, root=root, threshold=threshold)


__all__ = [
    "AtomProposal",
    "ChunkIndex",
    "CompileResult",
    "CompilerTools",
    "Provenance",
    "Review",
    "approve",
    "chunk_index",
    "compile",
    "gaps",
    "get_proposed",
    "grounded_noul",
    "ingest_source",
    "list_proposed",
    "load_questions",
    "register_cli",
    "register_mcp",
    "reject",
    "review",
    "search_chunks",
    "search_index",
    "similar_atoms",
    "structured_provenance",
]
