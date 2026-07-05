from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field
from sldb import StructuredNLDoc


class KnowledgeQuestion(StrEnum):
    WHAT = "what"
    WHY = "why"
    HOW = "how"
    HOW_NOT = "how_not"
    WHEN = "when"
    WHERE = "where"
    FOR_WHOM = "for_whom"


KnowledgeTag = Annotated[
    str,
    Field(
        pattern=r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_-]*$",
        description="Etiqueta semántica namespaced en la forma namespace:value.",
    ),
]


class ProvenanceRef(BaseModel):
    source_path: str = Field(description="Ruta al documento fuente dentro del repositorio.")
    source_title: str = Field(description="Título corto de la fuente.")
    chapter: str | None = Field(default=None, description="Capítulo de la fuente, si aplica.")
    section: str | None = Field(default=None, description="Sección de la fuente, si aplica.")
    page_start: int | None = Field(default=None, description="Página inicial relevante.")
    page_end: int | None = Field(default=None, description="Página final relevante.")
    anchor_text: str = Field(
        description="Texto ancla corto que permita ubicar el párrafo exacto en la fuente."
    )
    excerpt: str | None = Field(
        default=None,
        description="Cita breve o extracto del párrafo de origen.",
    )


class SourceNoteDoc(StructuredNLDoc):
    __semantics__ = {
        "type": ["knowledge", "source-note"],
        "workspace": ["knowledge", "source-notes"],
    }
    __template__ = """
---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
source_path: ⸢rev•source_path⸥
source_title: ⸢rev•source_title⸥
chapter: ⸢rev•chapter⸥
section: ⸢rev•section⸥
page_start: ⸢rev•page_start⸥
page_end: ⸢rev•page_end⸥
anchor_text: ⸢rev•anchor_text⸥
excerpt: ⸢rev•excerpt⸥
tags: ⸢rev•tags⸥
---

# ⸢render•title⸥

## Nota

⸢rev•note⸥
""".strip()

    id: str = Field(description="Identificador estable de la nota fuente.")
    title: str = Field(description="Título corto de la nota fuente.")
    source_path: str = Field(description="Ruta al documento fuente dentro del repositorio.")
    source_title: str = Field(description="Título corto de la fuente.")
    chapter: str | None = Field(default=None, description="Capítulo de la fuente, si aplica.")
    section: str | None = Field(default=None, description="Sección de la fuente, si aplica.")
    page_start: int | None = Field(default=None, description="Página inicial relevante.")
    page_end: int | None = Field(default=None, description="Página final relevante.")
    anchor_text: str = Field(description="Texto ancla para llegar al párrafo de origen.")
    excerpt: str = Field(description="Extracto breve del texto fuente que sostiene la nota.")
    note: str = Field(description="Nota estructurada derivada del fragmento fuente.")
    tags: list[KnowledgeTag] = Field(
        default_factory=list,
        description="Etiquetas semánticas para agrupación y búsqueda.",
    )


class KnowledgeAtomDoc(StructuredNLDoc):
    __semantics__ = {
        "type": ["knowledge", "atom"],
        "workspace": ["knowledge", "atoms"],
    }
    __template__ = """
---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
question: ⸢rev•question⸥
provenance: ⸢rev•provenance⸥
tags: ⸢rev•tags⸥
---

# ⸢render•title⸥

## Respuesta

⸢rev•answer⸥
""".strip()

    id: str = Field(description="Identificador estable del átomo de conocimiento.")
    title: str = Field(description="Título corto del átomo.")
    question: KnowledgeQuestion = Field(
        description="La pregunta 5WH1+ que este átomo responde."
    )
    answer: str = Field(description="Respuesta atómica y durable.")
    provenance: list[ProvenanceRef] = Field(
        default_factory=list,
        description="Referencias precisas a los párrafos fuente que sostienen el átomo.",
    )
    tags: list[KnowledgeTag] = Field(
        default_factory=list,
        description="Etiquetas semánticas para agrupación y búsqueda.",
    )
