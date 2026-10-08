"""Documentos de la KB que no son conocimiento: las categorías de tags editoriales.

`kb` las reconoce por el tag semántico `type.kb.category` (regla V5): con
`categories: required` en `kb.yaml`, todo tag editorial debe caer bajo una categoría
declarada (su tag completo o su namespace). Mismos campos que `TagNamespaceDoc` del
esquema de referencia y que `kb_base.CategoryDoc` (id, title, tag, parent, meaning).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from sldb import StructuredNLDoc


class TagNamespaceDoc(StructuredNLDoc):
    """Una categoría: un namespace de tags editoriales y cuándo usarlo."""

    __family__ = "kb"
    __semantics__ = {"type": ["kb", "category"], "workspace": ["knowledge"]}
    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
tag: ⸢rev•tag⸥
parent: ⸢optrev•parent⸥
kind: ⸢rev•kind⸥
examples: ⸢rev•examples⸥
---

# ⸢render•title⸥

## Meaning

⸢rev•meaning⸥

## Use When

⸢rev•use_when⸥

## Do Not Use When

⸢rev•do_not_use_when⸥
""".strip()

    id: str = Field(description="'category-<namespace>'.")
    title: str = Field(description="Nombre legible del namespace.")
    tag: str = Field(description="El namespace de tag que esta categoría declara (ej. topic).")
    parent: str | None = Field(default=None, description="El tag de la categoría padre; None en las raíces.")
    kind: Literal["family", "transversal"] = Field(description="Familia (raíz del árbol) o transversal.")
    examples: list[str] = Field(default_factory=list, description="Tags de ejemplo del namespace.")
    meaning: str = Field(description="Qué agrupa el namespace.")
    use_when: str = Field(description="Cuándo usar un tag de este namespace.")
    do_not_use_when: str = Field(description="Cuándo no usarlo.")
