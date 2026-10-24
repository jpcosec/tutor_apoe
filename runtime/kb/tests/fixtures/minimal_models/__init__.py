"""Modelos de la KB mínima de las pruebas (spec 01 §8.1): los justos para ejercer cada regla."""

from typing import Any

from pydantic import Field
from sldb import StructuredNLDoc

from kb_base import CategoryDoc, ReferenceConversation, ToolTest


class Note(StructuredNLDoc):
    """Un modelo con tags editoriales y __family__."""

    __family__ = "notes"
    __semantics__ = {"type": ["knowledge", "note"]}
    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
tags: ⸢rev•tags⸥
---

# ⸢render•title⸥

## Body

⸢rev•body⸥
""".strip()

    id: str = Field(description="Igual al nombre.")
    title: str = Field(description="Título.")
    tags: list[str] = Field(default_factory=list, description="Tags editoriales.")
    body: str = Field(description="Contenido.")


class SpecialNote(Note):
    """Subclase de Note con plantilla propia: `{Note+}` la incluye."""

    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
tags: ⸢rev•tags⸥
level: ⸢rev•level⸥
---

# ⸢render•title⸥

## Body

⸢rev•body⸥
""".strip()

    level: int = Field(description="Nivel.")


class Tool(StructuredNLDoc):
    """Una tool declarada; su name vive en `parameters`, como en las KBs reales."""

    __family__ = "self"
    __semantics__ = {"type": ["knowledge", "tool"]}
    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
---

# ⸢render•title⸥

## Parameters

⸢rev•parameters⸥
""".strip()

    id: str = Field(description="Igual al nombre.")
    title: str = Field(description="Título.")
    parameters: str = Field(description="JSON con name y parameters.")


class Trait(StructuredNLDoc):
    __family__ = "user"
    __semantics__ = {"type": ["knowledge", "trait"]}
    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
applies_when: ⸢optrev•applies_when⸥
---

# ⸢render•title⸥
""".strip()

    id: str = Field(description="Igual al nombre.")
    title: str = Field(description="Título.")
    applies_when: list[str] | None = Field(default=None, description="Condiciones.")


class Style(StructuredNLDoc):
    __family__ = "self"
    __semantics__ = {"type": ["knowledge", "style"]}
    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
applies_when: ⸢optrev•applies_when⸥
---

# ⸢render•title⸥
""".strip()

    id: str = Field(description="Igual al nombre.")
    title: str = Field(description="Título.")
    applies_when: list[str] | None = Field(default=None, description="Condiciones.")


class Step(StructuredNLDoc):
    __family__ = "conversation"
    __semantics__ = {"type": ["knowledge", "step"]}
    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
tags: ⸢rev•tags⸥
---

# ⸢render•title⸥
""".strip()

    id: str = Field(description="Igual al nombre.")
    title: str = Field(description="Título.")
    tags: list[str] = Field(default_factory=list, description="Tags editoriales.")


class Category(CategoryDoc):
    """Subclase de la categoría base (§4.3)."""


class Reference(ReferenceConversation):
    """Subclase de la conversación de referencia base (§4.5)."""


class ToolCheck(ToolTest):
    """Subclase de la prueba de tool base (§4.6)."""


def payload(**fields: Any) -> dict[str, Any]:
    return fields
