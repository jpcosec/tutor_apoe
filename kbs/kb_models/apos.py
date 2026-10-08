"""Átomos de conocimiento y nodos de la taxonomía APOS.

Espejo tipado de los `.md` de `desk/atoms/`: mismo `id`, `title`, `five_wh_one_plus`, `tags`,
cuerpo `## Respuesta` y `## Procedencia`. `node_type: knowledge` → `KnowledgeAtom`
(`SourceAtom` si habla del libro fuente); `node_type: branch` → `BranchNode`; `parent_id` →
`parent` más una arista `child_of`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field
from sldb import StructuredNLDoc


class AtomQuestion(StrEnum):
    """La pregunta 5WH1+ que responde un átomo (igual que `DomainAtom` del esquema de referencia)."""

    WHAT = "what"
    WHY = "why"
    HOW = "how"
    HOW_NOT = "how_not"
    WHEN = "when"
    WHERE = "where"
    FOR_WHOM = "for_whom"


AtomTag = Annotated[
    str,
    Field(
        pattern=r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_.-]*$",
        description="Tag editorial con namespace, en la forma namespace:valor.",
    ),
]


class KnowledgeAtom(StructuredNLDoc):
    """Una unidad de conocimiento sobre la teoría APOS: una pregunta, una respuesta, una fuente."""

    __family__ = "knowledge"
    __semantics__ = {"type": ["knowledge", "atom"], "workspace": ["knowledge"]}
    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
five_wh_one_plus: ⸢rev•five_wh_one_plus⸥
tags: ⸢rev•tags⸥
parent: ⸢optrev•parent⸥
---

# ⸢render•title⸥

## Respuesta

⸢rev•answer⸥

## Procedencia

⸢rev•provenance⸥
""".strip()

    id: str = Field(description="Identificador estable, igual al nombre del documento; 'atom-<slug>'.")
    title: str = Field(description="Título corto y descriptivo.")
    five_wh_one_plus: AtomQuestion = Field(description="La única pregunta 5WH1+ que responde el átomo.")
    tags: list[AtomTag] = Field(default_factory=list, description="Tags editoriales (system:, topic:, …).")
    parent: str | None = Field(
        default=None,
        description="Nombre del BranchNode padre; proyección legible de la arista child_of.",
    )
    answer: str = Field(description="La respuesta curada a la pregunta.")
    provenance: str = Field(description="De dónde sale: fuente, capítulo, sección.")


class SourceAtom(KnowledgeAtom):
    """Un átomo sobre la fuente misma (autoría, propósito, alcance, estructura del libro)."""

    __family__ = "sources"
    __semantics__ = {"type": ["knowledge", "atom", "source"], "workspace": ["knowledge"]}


class BranchNode(StructuredNLDoc):
    """Un nodo de organización de la taxonomía: agrupa átomos y otras ramas."""

    __family__ = "taxonomy"
    __semantics__ = {"type": ["knowledge", "branch"], "workspace": ["knowledge"]}
    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
tags: ⸢rev•tags⸥
parent: ⸢optrev•parent⸥
---

# ⸢render•title⸥

## Descripción

⸢rev•description⸥

## Procedencia

⸢rev•provenance⸥
""".strip()

    id: str = Field(description="Identificador estable, igual al nombre del documento; 'branch-<slug>'.")
    title: str = Field(description="Nombre de la rama.")
    tags: list[AtomTag] = Field(default_factory=list, description="Tags editoriales.")
    parent: str | None = Field(default=None, description="Nombre del BranchNode padre; None en la raíz.")
    description: str = Field(description="Qué agrupa esta rama.")
    provenance: str = Field(description="De dónde sale la rama (taxonomía del repo o inferida).")
