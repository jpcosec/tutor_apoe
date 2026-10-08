"""Fuentes crudas ingeridas y sus fragmentos (`tutor.ingest`).

Materia prima para proponer átomos, no conocimiento curado: un `SourceDoc` por fuente (un
archivo o un texto pegado) y un `SourceChunk` por fragmento. Quedan fuera del índice de
embeddings porque `kb.yaml` indexa solo `KnowledgeAtom` (`index.models`), y fuera de lo que
ve el tutor porque `projection-tutor` nombra solo `KnowledgeAtom` y `BranchNode`. Su tag
semántico `type.source.*` (familia `ingest`) los distingue de `type.knowledge.*`; la
procedencia de un átomo apunta al `chunk_id` del que salió.
"""

from __future__ import annotations

from pydantic import Field
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
    text: str = Field(description="El fragmento tal cual (encabezados demotidos a negrita).")
