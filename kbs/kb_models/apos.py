"""Átomos de conocimiento y nodos de la taxonomía APOS.

Espejo tipado de los `.md` de `desk/atoms/`: mismo `id`, `title`, `five_wh_one_plus`, `tags`,
cuerpo `## Respuesta` y `## Procedencia`. `node_type: knowledge` → `KnowledgeAtom`
(`SourceAtom` si habla del libro fuente); `node_type: branch` → `BranchNode`; `parent_id` →
`parent` más una arista `child_of`.

La procedencia es estructurada (`kb_models.provenance.Provenance`, en el frontmatter) y la
sección `## Procedencia` (`citation`) se renderiza desde ella; en las ramas, `coverage` es la
unión de la procedencia de sus descendientes y su `## Procedencia` se renderiza desde ahí.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import Field, model_validator
from sldb import StructuredNLDoc

from .provenance import Coverage, Provenance, render_coverage, render_provenance


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
provenance: ⸢rev•provenance⸥
---

# ⸢render•title⸥

## Respuesta

⸢rev•answer⸥

## Procedencia

⸢rev•citation⸥
""".strip()

    id: str = Field(description="Identificador estable, igual al nombre del documento; 'atom-<slug>'.")
    title: str = Field(description="Título corto y descriptivo.")
    five_wh_one_plus: AtomQuestion = Field(description="La única pregunta 5WH1+ que responde el átomo.")
    tags: list[AtomTag] = Field(default_factory=list, description="Tags editoriales (system:, topic:, …).")
    parent: str | None = Field(
        default=None,
        description="Nombre del BranchNode padre; proyección legible de la arista child_of.",
    )
    provenance: list[Provenance] = Field(
        default_factory=list,
        description="De dónde sale, estructurado: fuente, capítulo, secciones, páginas, fragmentos que lo respaldan.",
    )
    answer: str = Field(description="La respuesta curada a la pregunta.")
    citation: str = Field(default="", description="La procedencia en prosa corta, renderizada desde `provenance`.")

    @model_validator(mode="after")
    def _render_citation(self) -> KnowledgeAtom:
        self.citation = render_provenance(self.provenance, with_excerpt=True)
        return self


class SourceAtom(KnowledgeAtom):
    """Un átomo sobre la fuente misma (autoría, propósito, alcance, estructura del libro)."""

    __family__ = "sources"
    __semantics__ = {"type": ["knowledge", "atom", "source"], "workspace": ["knowledge"]}


class BranchNode(StructuredNLDoc):
    """Un nodo de la taxonomía: agrupa átomos y otras ramas, y cubre un tramo de la fuente."""

    __family__ = "taxonomy"
    __semantics__ = {"type": ["knowledge", "branch"], "workspace": ["knowledge"]}
    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
tags: ⸢rev•tags⸥
parent: ⸢optrev•parent⸥
coverage: ⸢optrev•coverage⸥
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
    coverage: Coverage | None = Field(default=None, description="Unión de la procedencia de sus descendientes (derivada en el build).")
    description: str = Field(description="Qué abarca la rama y cómo se relaciona con sus hermanas.")
    provenance: str = Field(default="", description="Prosa renderizada desde `coverage` («Cubre … cap. 3 §3.2–3.4, pp. 20–41; 7 átomos»).")

    @model_validator(mode="after")
    def _render_provenance(self) -> BranchNode:
        if self.coverage is not None:
            self.provenance = render_coverage(self.coverage)
        elif not self.provenance:
            self.provenance = "Rama sin cobertura calculada todavía."
        return self


def provenance_items(payload: dict[str, Any]) -> list[Provenance]:
    """La procedencia de un payload (átomo) como objetos, tolerando dicts crudos o listas vacías."""
    return [Provenance.model_validate(p) if not isinstance(p, Provenance) else p for p in payload.get("provenance") or []]
