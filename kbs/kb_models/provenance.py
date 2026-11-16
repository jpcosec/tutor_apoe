"""Procedencia estructurada: la dirección en la fuente desde donde un átomo se verifica.

Un átomo no «viene de un script»: viene de un tramo de texto. `Provenance` es esa dirección,
estable y navegable en los dos sentidos (átomo → pasaje, pasaje → átomos):

- `kind`: `book` (un pasaje de una fuente ingerida), `expert` (conversación de curación) o
  `derived` (calculada a partir de otros documentos, p. ej. la cobertura de una rama).
- `source` + `chapter` + `sections`: la dirección editorial (`doc_address`): qué libro, qué
  capítulo, qué secciones (numéricas como `3.2.1` o partes con nombre como `Prefacio`).
- `pages` + `chunk_ids` + `excerpt`: la dirección física (`local_address`): páginas del PDF,
  fragmentos `SourceChunk` que respaldan la afirmación (confirmados con Jev, `nouls`) y la
  oración más parecida del mejor fragmento.
- `anchored`: `True` si algún fragmento respalda el átomo (noul ≥ umbral), `False` si se buscó
  y no hubo respaldo (átomo *unanchored*), `None` si no se evaluó (expertos, derivados).

La prosa de `## Procedencia` («Arnon et al. (2014), cap. 3 §3.2.1, pp. 23–25») se RENDERIZA
desde aquí con `render_provenance`; nunca al revés. `parse_provenance_prose` existe solo para
leer los átomos fuente de `desk/atoms/`, escritos a mano en prosa regular.
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

#: Fuente por defecto de la KB APOS y cómo se cita.
DEFAULT_SOURCE = "source-arnon-et-al-2014-apos-theory"
SOURCE_LABELS: dict[str, str] = {DEFAULT_SOURCE: "Arnon et al. (2014)"}
#: Cómo reconocer la fuente en la prosa de `desk/atoms/` (fragmento del nombre del PDF o del autor).
SOURCE_ALIASES: dict[str, str] = {"arnon": DEFAULT_SOURCE}
#: Partes con nombre del libro (fuera de la numeración de capítulos), tal como se citan.
NAMED_PARTS: dict[str, str] = {
    "prefacio": "Prefacio",
    "tabla de contenidos": "Tabla de contenidos",
    "introduccion": "Introducción",
}
EXPERT_LABEL = "Conversación de curación con experto"


class ProvenanceKind(StrEnum):
    BOOK = "book"
    EXPERT = "expert"
    DERIVED = "derived"


class Provenance(BaseModel):
    """Una dirección en la fuente: editorial (capítulo/sección) y física (páginas/fragmentos)."""

    kind: ProvenanceKind = Field(description="book | expert | derived.")
    source: str | None = Field(default=None, description="Id del SourceDoc ingerido (None si no es un libro).")
    chapter: int | None = Field(default=None, description="Capítulo de la fuente, si aplica.")
    sections: list[str] = Field(default_factory=list, description="Secciones numéricas (`3.2.1`) o partes con nombre (`Prefacio`).")
    pages: list[int] | None = Field(default=None, description="[primera, última] página del PDF que respalda el átomo.")
    excerpt: str | None = Field(default=None, description="La oración del mejor fragmento más parecida a la respuesta.")
    chunk_ids: list[str] = Field(default_factory=list, description="SourceChunk que respaldan la afirmación (noul ≥ umbral), de mejor a peor.")
    nouls: list[float] = Field(default_factory=list, description="Noul de Jev de cada chunk_id, en el mismo orden.")
    anchored: bool | None = Field(default=None, description="True con respaldo; False buscado sin respaldo; None no evaluado.")
    note: str | None = Field(default=None, description="Matiz en prosa (fecha de la conversación, «especialmente el ejemplo…»).")

    @field_validator("pages")
    @classmethod
    def _pages_pair(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if len(value) != 2 or value[0] > value[1] or value[0] < 1:
            raise ValueError("pages debe ser [primera, última] con primera <= última")
        return [int(value[0]), int(value[1])]

    @field_validator("sections")
    @classmethod
    def _sections_sorted(cls, value: list[str]) -> list[str]:
        return sorted(dict.fromkeys(s.strip() for s in value if s.strip()), key=section_key)

    @property
    def numeric_sections(self) -> list[str]:
        return [s for s in self.sections if SECTION_NUMBER.fullmatch(s)]

    @property
    def named_parts(self) -> list[str]:
        return [s for s in self.sections if not SECTION_NUMBER.fullmatch(s)]

    @property
    def label(self) -> str:
        return source_label(self.source)


class Coverage(BaseModel):
    """Lo que una rama cubre de la fuente: la unión de la procedencia de sus descendientes."""

    sources: list[str] = Field(default_factory=list, description="SourceDoc cubiertos.")
    chapters: list[int] = Field(default_factory=list, description="Capítulos cubiertos, ordenados.")
    sections: list[str] = Field(default_factory=list, description="Secciones cubiertas, ordenadas.")
    pages: list[int] | None = Field(default=None, description="[primera, última] página cubierta.")
    chunk_ids: list[str] = Field(default_factory=list, description="Fragmentos anclados por sus descendientes.")
    n_atoms: int = Field(default=0, description="Átomos de conocimiento descendientes.")
    n_expert: int = Field(default=0, description="Cuántos descendientes vienen de conversación con experto.")
    n_unanchored: int = Field(default=0, description="Cuántos descendientes buscaron respaldo y no lo hallaron.")

    @field_validator("sections")
    @classmethod
    def _sections_sorted(cls, value: list[str]) -> list[str]:
        return sorted(dict.fromkeys(value), key=section_key)


# -- helpers ----------------------------------------------------------------------------------

SECTION_NUMBER = re.compile(r"\d+(?:\.\d+)+")


def section_key(section: str) -> tuple[int, tuple[int, ...] | str]:
    """Orden natural: `3.2.1` < `3.10`; las partes con nombre van antes, por nombre."""
    if SECTION_NUMBER.fullmatch(section):
        return (1, tuple(int(p) for p in section.split(".")))
    return (0, section.lower())


def source_label(source: str | None) -> str:
    if source is None:
        return "fuente no identificada"
    return SOURCE_LABELS.get(source, source)


def _strip_accents(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


# -- render -----------------------------------------------------------------------------------


def _pages_text(pages: list[int] | None) -> str:
    if not pages:
        return ""
    first, last = pages
    return f"p. {first}" if first == last else f"pp. {first}–{last}"


def _entry_text(item: Provenance, *, with_pages: bool = True) -> str:
    parts: list[str] = []
    if item.chapter is not None:
        head = f"cap. {item.chapter}"
        numeric = item.numeric_sections
        if numeric:
            head += " §" + ", ".join(numeric)
        parts.append(head)
    elif item.numeric_sections:
        parts.append("§" + ", ".join(item.numeric_sections))
    parts.extend(p.lower() if p in NAMED_PARTS.values() else p for p in item.named_parts)
    text = ", ".join(parts)
    if item.note:
        text = f"{text} ({item.note})" if text else item.note
    if with_pages and item.pages:
        text = f"{text}, {_pages_text(item.pages)}" if text else _pages_text(item.pages)
    return text


def render_provenance(items: list[Provenance] | list[dict[str, Any]], *, with_pages: bool = True, with_excerpt: bool = False) -> str:
    """Prosa corta y legible: «Arnon et al. (2014), cap. 3 §3.2.1, pp. 23–25; cap. 7, pp. 117–120».
    Con `with_excerpt`, agrega la cita del mejor fragmento entre comillas angulares."""
    parsed = [i if isinstance(i, Provenance) else Provenance.model_validate(i) for i in items]
    if not parsed:
        return "Sin procedencia registrada."
    pieces: list[str] = []
    index = 0
    while index < len(parsed):
        item = parsed[index]
        if item.kind == ProvenanceKind.EXPERT:
            pieces.append(f"{EXPERT_LABEL}" + (f" ({item.note})" if item.note else ""))
            index += 1
            continue
        if item.kind == ProvenanceKind.DERIVED:
            pieces.append(item.note or "Derivada de otros documentos de la KB")
            index += 1
            continue
        group = [item]
        while index + len(group) < len(parsed) and parsed[index + len(group)].kind == ProvenanceKind.BOOK and parsed[index + len(group)].source == item.source:
            group.append(parsed[index + len(group)])
        inner = "; ".join(t for t in (_entry_text(g, with_pages=with_pages) for g in group) if t)
        pieces.append(f"{item.label}, {inner}" if inner else item.label)
        index += len(group)
    text = "; ".join(pieces)
    if not text.endswith("."):
        text += "."
    if with_excerpt:
        excerpt = next((i.excerpt for i in parsed if i.excerpt), None)
        if excerpt:
            text += f" «{excerpt}»"
    return text


#: Con secciones de más capítulos que esto, la cobertura dice cuántas son en vez de enumerarlas.
MAX_SECTION_GROUPS = 4


def compact_sections(sections: list[str]) -> str:
    """`['3.2','3.3','3.4','3.5']` → `§3.2–3.5`; pocas → `§3.2, 3.4`; de varios capítulos → `§3.2–3.5, 7.1–7.7`;
    de muchos capítulos → `23 secciones`; partes con nombre al final."""
    numeric = sorted((s for s in sections if SECTION_NUMBER.fullmatch(s)), key=section_key)
    named = [s.lower() for s in sections if not SECTION_NUMBER.fullmatch(s)]
    out: list[str] = []
    if numeric:
        groups: dict[str, list[str]] = {}
        for section in numeric:
            groups.setdefault(section.split(".")[0], []).append(section)
        if len(groups) > MAX_SECTION_GROUPS:
            out.append(f"{len(numeric)} secciones")
        else:
            out.append("§" + ", ".join(f"{g[0]}–{g[-1]}" if len(g) > 3 else ", ".join(g) for g in groups.values()))
    out.extend(named)
    return ", ".join(out)


def compact_chapters(chapters: list[int]) -> str:
    if not chapters:
        return ""
    runs: list[list[int]] = []
    for chapter in sorted(set(chapters)):
        if runs and chapter == runs[-1][-1] + 1:
            runs[-1].append(chapter)
        else:
            runs.append([chapter])
    text = ", ".join(f"{r[0]}–{r[-1]}" if len(r) > 1 else str(r[0]) for r in runs)
    return f"cap. {text}"


def render_coverage(coverage: Coverage | dict[str, Any]) -> str:
    """«Cubre Arnon et al. (2014) cap. 3 §3.2–3.4, pp. 20–41; 7 átomos (1 de conversación con experto).»"""
    cov = coverage if isinstance(coverage, Coverage) else Coverage.model_validate(coverage)
    atoms = f"{cov.n_atoms} átomo" + ("" if cov.n_atoms == 1 else "s")
    extras: list[str] = []
    if cov.n_expert:
        extras.append(f"{cov.n_expert} de conversación con experto")
    if cov.n_unanchored:
        extras.append(f"{cov.n_unanchored} sin anclaje en la fuente")
    tail = atoms + (f" ({', '.join(extras)})" if extras else "")
    if not cov.sources and not cov.chapters and not cov.sections:
        return f"Agrupa {tail}." if cov.n_atoms else "Rama sin átomos todavía."
    where = [compact_chapters(cov.chapters), compact_sections(cov.sections), _pages_text(cov.pages)]
    label = ", ".join(source_label(s) for s in cov.sources) or "la fuente"
    return f"Cubre {label} " + ", ".join(w for w in where if w) + f"; {tail}."


# -- parser de la prosa de desk/atoms ----------------------------------------------------------

_EXPERT = re.compile(r"conversaci[oó]n de curaci[oó]n con experto[,:]?\s*(\d{4}-\d{2}-\d{2})?", re.I)
_CHAPTERS = re.compile(r"cap[ií]tulos?\s+((?:\d+)(?:\s*,\s*\d+)*(?:\s*(?:y|e)\s*\d+)?)", re.I)
_SECTIONS = re.compile(r"secci(?:[oó]n|ones)\s+((?:\d+(?:\.\d+)+)(?:\s*,\s*\d+(?:\.\d+)+)*(?:\s*(?:,\s*)?(?:y|e)\s*\d+(?:\.\d+)+)?)", re.I)
_NUMBERS = re.compile(r"\d+(?:\.\d+)*")
_PREFIX = re.compile(r"^\s*fuente principal\s*:\s*", re.I)
_TAIL = re.compile(r",?\s*(?:en el texto\s+)?extra[ií]do desde(?: el pdf ubicado en)?\s*`[^`]*`\.?\s*$", re.I)
_BOOK = re.compile(r",?\s*(?:del|en el)\s+libro de arnon et al\.? \(2014\),?", re.I)
_PURE = re.compile(
    r"^(?:(?:cap[ií]tulos?|secci(?:[oó]n|ones)|y|e|,|\d+(?:\.\d+)*|del|prefacio|tabla de contenidos|introducci[oó]n)\s*)+$",
    re.I,
)


class ProvenanceParseError(ValueError):
    """La prosa no sigue ninguna de las formas conocidas."""


def _note_from(core: str) -> str | None:
    """Las cláusulas (separadas por coma) que no son enumeración pura de capítulos/secciones:
    «Capítulo 3, sección 3.2.4, especialmente el ejemplo de composición de funciones» →
    «especialmente el ejemplo de composición de funciones»."""
    clauses = [c.strip(" .;") for c in core.split(",")]
    kept = [c for c in clauses if c and not _PURE.fullmatch(_strip_accents(c.lower()))]
    return ", ".join(kept) or None


def parse_provenance_prose(text: str, *, default_source: str = DEFAULT_SOURCE, strict: bool = False) -> list[Provenance]:
    """La prosa de `## Procedencia` de un átomo fuente → `[Provenance]`.

    Formas reconocidas (todas las de `desk/atoms/`): «Fuente principal: Capítulo 3, sección 3.2.1,
    del libro de Arnon et al. (2014), extraído desde `…pdf`.» con variantes («secciones 3.1 y 3.2»,
    «Capítulos 2 y 5», «presentación del Capítulo 4», «prefacio del libro», «tabla de contenidos e
    introducción»), y «Conversacion de curacion con experto, AAAA-MM-DD.». Un capítulo por entrada;
    las secciones cuelgan del capítulo que nombran; lo que no es enumeración pura queda en `note`.
    Sin forma conocida: `ProvenanceParseError` con `strict`, si no una entrada `derived` con la prosa."""
    raw = " ".join(str(text or "").split())
    if not raw:
        if strict:
            raise ProvenanceParseError("procedencia vacía")
        return []
    expert = _EXPERT.search(raw)
    if expert:
        return [Provenance(kind=ProvenanceKind.EXPERT, note=expert.group(1) or None)]
    core = _PREFIX.sub("", raw)
    core = _TAIL.sub("", core)
    plain = _strip_accents(core.lower())
    source = next((sid for alias, sid in SOURCE_ALIASES.items() if alias in plain), None)
    core = re.sub(r"\s*,(\s*,)+", ",", _BOOK.sub(", ", core)).strip(" .,;")
    chapters: list[int] = []
    for match in _CHAPTERS.finditer(core):
        for number in _NUMBERS.findall(match.group(1)):
            if int(number) not in chapters:
                chapters.append(int(number))
    sections: list[str] = []
    for match in _SECTIONS.finditer(core):
        for number in _NUMBERS.findall(match.group(1)):
            if "." in number and number not in sections:
                sections.append(number)
    named = [label for key, label in NAMED_PARTS.items() if key in _strip_accents(core.lower())]
    if "Introducción" in named and (chapters or re.search(r"cap[ií]tulo 1\b", core, re.I)):
        named.remove("Introducción")  # «Capítulo 1, Introducción»: la introducción ES el capítulo 1
    if not chapters and not sections and not named:
        if strict:
            raise ProvenanceParseError(f"procedencia sin forma conocida: {raw!r}")
        return [Provenance(kind=ProvenanceKind.DERIVED, note=raw)]
    for section in sections:  # una sección nombra su capítulo aunque la prosa no lo diga
        chapter = int(section.split(".")[0])
        if chapter not in chapters:
            chapters.append(chapter)
    note = _note_from(core)
    entries: list[Provenance] = []
    for position, chapter in enumerate(chapters):
        entries.append(
            Provenance(
                kind=ProvenanceKind.BOOK,
                source=source or default_source,
                chapter=chapter,
                sections=[s for s in sections if int(s.split(".")[0]) == chapter],
                note=note if position == 0 else None,
            )
        )
    for part in named:
        entries.append(Provenance(kind=ProvenanceKind.BOOK, source=source or default_source, sections=[part], note=None if entries else note))
    return entries


__all__ = [
    "Coverage",
    "DEFAULT_SOURCE",
    "EXPERT_LABEL",
    "NAMED_PARTS",
    "Provenance",
    "ProvenanceKind",
    "ProvenanceParseError",
    "SOURCE_LABELS",
    "compact_chapters",
    "compact_sections",
    "parse_provenance_prose",
    "render_coverage",
    "render_provenance",
    "section_key",
    "source_label",
]
