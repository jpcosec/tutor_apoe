"""GrupoDoc: un grupo de atomos (un tag con puntos) hecho documento, para que una relacion pueda tenerlo de extremo."""

from __future__ import annotations

from pydantic import Field

from sldb import StructuredNLDoc


class GrupoDoc(StructuredNLDoc):
    """Un grupo de atomos. Una relacion cuyo extremo es `GrupoDoc:<slug>` la heredan todos los atomos del tag
    (y de sus subgrupos). El nombre del documento es el tag con los puntos cambiados por guiones."""

    __semantics__ = {"type": ["knowledge", "group"]}
    __template__ = """
---
tag: ⸢rev•tag⸥
---

# ⸢rev•title⸥

⸢rev,markdown•description⸥
""".strip()
    title: str = Field(description="Nombre legible del grupo.")
    tag: str = Field(description="Tag del grupo, con puntos para la jerarquia (infra.ingesta).")
    description: str = Field(default="", description="Para que sirve el grupo; texto libre en markdown.")
