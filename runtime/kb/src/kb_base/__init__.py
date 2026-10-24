"""Modelos base opcionales que una KB puede registrar o subclasificar (spec 01 §4.3, §4.5, §4.6; D3, D7, D12).

El módulo `kb` no los busca por clase sino por su tag semántico, así que una KB
puede declarar los suyos propios sin heredar de aquí.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field
from sldb import StructuredNLDoc


class CategoryDoc(StructuredNLDoc):
    """Una categoría de tags editoriales: un tag completo o su namespace, y su padre."""

    __semantics__ = {"type": ["kb", "category"]}
    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
tag: ⸢rev•tag⸥
parent: ⸢optrev•parent⸥
---

# ⸢render•title⸥

## Meaning

⸢rev•meaning⸥
""".strip()

    id: str = Field(description="Identificador; igual al nombre del documento (D5).")
    title: str = Field(description="Nombre legible.")
    tag: str = Field(description="Tag completo o namespace que declara.")
    parent: str | None = Field(default=None, description="Tag de la categoría padre; None en las raíces.")
    meaning: str = Field(description="Qué agrupa.")


class ReferenceTurn(BaseModel):
    """Un turno de una conversación de referencia."""

    who: Literal["user", "agent"] = Field(description="Quién habla.")
    text: str = Field(description="Lo que dice.")
    expect: dict[str, Any] | None = Field(
        default=None, description="Lo que el consumidor comprueba tras el turno."
    )


class ReferenceConversation(StructuredNLDoc):
    """Una conversación de referencia; qué significa `expect` lo define el consumidor."""

    __semantics__ = {"type": ["kb", "reference"]}
    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
turns: ⸢rev•turns⸥
---

# ⸢render•title⸥

## Purpose

⸢rev•purpose⸥
""".strip()

    id: str = Field(description="Identificador; igual al nombre del documento (D5).")
    title: str = Field(description="Qué caso cubre.")
    turns: list[ReferenceTurn] = Field(description="Los turnos.")
    purpose: str = Field(description="Por qué existe.")


class ToolTest(StructuredNLDoc):
    """Una prueba de comportamiento de una tool declarada en la KB."""

    __semantics__ = {"type": ["kb", "tool_test"]}
    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
tool: ⸢rev•tool⸥
args: ⸢rev•args⸥
expect: ⸢rev•expect⸥
---

# ⸢render•title⸥

## Purpose

⸢rev•purpose⸥
""".strip()

    id: str = Field(description="Identificador; igual al nombre del documento (D5).")
    title: str = Field(description="Qué comportamiento prueba.")
    tool: str = Field(description="El name de una tool declarada en la KB.")
    args: dict[str, Any] = Field(description="Argumentos de la llamada.")
    expect: dict[str, Any] = Field(description="Lo que se compara del resultado.")
    purpose: str = Field(description="Qué regla del negocio protege.")


__all__ = ["CategoryDoc", "ReferenceConversation", "ReferenceTurn", "ToolTest"]
