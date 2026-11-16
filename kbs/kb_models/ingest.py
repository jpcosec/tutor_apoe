"""Fuentes crudas ingeridas y sus fragmentos (`tutor.ingest`).

Materia prima para proponer átomos, no conocimiento curado: un `SourceDoc` por fuente (un
archivo o un texto pegado) y un `SourceChunk` por fragmento. Quedan fuera del índice de
embeddings porque `kb.yaml` indexa solo `KnowledgeAtom` (`index.models`), y fuera de lo que
ve el tutor porque `projection-tutor` nombra solo `KnowledgeAtom` y `BranchNode`. Su tag
semántico `type.source.*` (familia `ingest`) los distingue de `type.knowledge.*`; la
procedencia de un átomo apunta al `chunk_id` del que salió.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sldb import StructuredNLDoc


class SourceDoc(StructuredNLDoc):
    """Una fuente ingerida: de dónde vino y en cuántos fragmentos quedó."""

    __family__ = "ingest"
    __semantics__ = {"type": ["source", "document"], "workspace": ["ingest"]}
    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
path: ⸢optrev•path⸥
n_chunks: ⸢rev•n_chunks⸥
---

# ⸢render•title⸥

## Descripción

⸢rev•description⸥
""".strip()

    id: str = Field(description="Identificador estable, igual al nombre del documento; 'source-<slug>'.")
    title: str = Field(description="Título de la fuente.")
    path: str | None = Field(default=None, description="Ruta o URL de origen, si la hubo.")
    n_chunks: int = Field(description="Cuántos SourceChunk produjo.")
    description: str = Field(description="Qué es la fuente y cómo se fragmentó.")


class OutlineEntry(BaseModel):
    """Una entrada de la tabla de contenidos ubicada en los fragmentos: capítulo, sección o parte."""

    number: str = Field(description="`3`, `3.2.1`, o el nombre de la parte (`Prefacio`, `Tabla de contenidos`).")
    title: str = Field(description="Título tal como aparece en la tabla de contenidos.")
    level: int = Field(description="0 parte/capítulo, 1 sección, 2 subsección…")
    printed_page: int | None = Field(default=None, description="Página impresa que declara la tabla de contenidos.")
    chunk_start: int | None = Field(default=None, description="`index` del primer SourceChunk de la entrada (donde está su encabezado).")
    chunk_end: int | None = Field(default=None, description="`index` del último SourceChunk antes de la siguiente entrada del mismo nivel o superior.")
    page_start: int | None = Field(default=None, description="Página del PDF donde empieza.")
    page_end: int | None = Field(default=None, description="Página del PDF donde termina.")
    found: bool = Field(default=False, description="Si el encabezado se localizó en el texto (si no, se interpoló por página impresa).")


class SourceOutline(StructuredNLDoc):
    """La estructura de una fuente (capítulos y secciones) mapeada a sus páginas y fragmentos."""

    __family__ = "ingest"
    __semantics__ = {"type": ["source", "outline"], "workspace": ["ingest"]}
    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
source: ⸢rev•source⸥
n_pages: ⸢rev•n_pages⸥
page_offset: ⸢optrev•page_offset⸥
entries: ⸢rev•entries⸥
---

# ⸢render•title⸥

## Descripción

⸢rev•description⸥
""".strip()

    id: str = Field(description="Identificador estable, igual al nombre del documento; 'toc-<source>'.")
    title: str = Field(description="Título (esquema de la fuente).")
    source: str = Field(description="Nombre del SourceDoc.")
    n_pages: int = Field(description="Última página del PDF con texto.")
    page_offset: int | None = Field(default=None, description="PDF − impresa, estimado en el capítulo 1 (orientativo: varía a lo largo del libro).")
    entries: list[OutlineEntry] = Field(default_factory=list, description="Entradas en el orden de la tabla de contenidos.")
    description: str = Field(description="Cómo se obtuvo el esquema y cuántas entradas se localizaron.")


class SourceChunk(StructuredNLDoc):
    """Un fragmento contiguo de una fuente, con su posición en el texto original."""

    __family__ = "ingest"
    __semantics__ = {"type": ["source", "chunk"], "workspace": ["ingest"]}
    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
source: ⸢rev•source⸥
index: ⸢rev•index⸥
start: ⸢rev•start⸥
end: ⸢rev•end⸥
page: ⸢optrev•page⸥
---

# ⸢render•title⸥

## Texto

⸢rev•text⸥
""".strip()

    id: str = Field(description="Identificador estable, igual al nombre del documento; '<source>-chunk-<n>'.")
    title: str = Field(description="Título del fragmento (fuente + número).")
    source: str = Field(description="Nombre del SourceDoc del que sale.")
    index: int = Field(description="Posición del fragmento dentro de la fuente, desde 0.")
    start: int = Field(description="Offset inicial (caracteres) en el texto original.")
    end: int = Field(description="Offset final (exclusivo) en el texto original.")
    page: int | None = Field(default=None, description="Página (desde 1) donde empieza el fragmento, si la fuente la tenía (PDF).")
    text: str = Field(description="El fragmento tal cual (encabezados demotidos a negrita).")
