"""Publicacion de un informe: foto inmutable (un documento por version, no se edita).

El informe se publica seccion por seccion (mismos headings que InformeAvanceDoc) y no como un unico
`body`: SLDB rechaza headings dentro de un field (ruido estructural) y un field `markdown` no
sobrevive al round-trip si trae headings; `rev,markdown` si conserva viñetas y parrafos.
"""

from __future__ import annotations

from pydantic import Field

from sldb import StructuredNLDoc


class PublicacionDoc(StructuredNLDoc):
    __semantics__ = {"type": ["knowledge", "publication"]}
    __template__ = """
---
informe: ⸢rev•informe⸥
version: ⸢rev•version⸥
atoms: ⸢rev•atoms⸥
---

# ⸢rev•title⸥

## Resumen

⸢rev,markdown•resumen⸥

## Decisiones

⸢rev,markdown•decisiones⸥

## Riesgos

⸢rev,markdown•riesgos⸥

## Pendientes

⸢rev,markdown•pendientes⸥
""".strip()
    informe: str = Field(description="Id del informe publicado.")
    version: int = Field(description="Numero de version, correlativo por informe.")
    atoms: list[str] = Field(default_factory=list, description="Rutas de los atomos incluidos en la foto.")
    title: str = Field(description="Titulo del informe al publicar.")
    resumen: str = Field(default="", description="Seccion Resumen tal como la renderiza SLDB.")
    decisiones: str = Field(default="", description="Seccion Decisiones tal como la renderiza SLDB.")
    riesgos: str = Field(default="", description="Seccion Riesgos tal como la renderiza SLDB.")
    pendientes: str = Field(default="", description="Seccion Pendientes tal como la renderiza SLDB.")
