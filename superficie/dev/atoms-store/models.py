"""Modelos del store demo de atomos: acta, atomos, relaciones tipadas e informe por slots."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from sldb import StructuredNLDoc


class ActaDoc(StructuredNLDoc):
    __template__ = """
# ⸢rev•title⸥

⸢rev,markdown•body⸥
""".strip()
    title: str = Field(description="Titulo del acta.")
    body: str = Field(description="Texto fuente completo.")


class AtomDoc(StructuredNLDoc):
    __semantics__ = {"type": ["knowledge", "atom"]}
    __references__ = ["source"]
    __template__ = """
---
kind: ⸢rev•kind⸥
status: ⸢rev•status⸥
source: ⸢rev•source⸥
source_field: ⸢rev•source_field⸥
start: ⸢rev•start⸥
end: ⸢rev•end⸥
conf: ⸢rev•conf⸥
tags: ⸢rev•tags⸥
---

# ⸢rev•text⸥

> ⸢rev•quote⸥
""".strip()
    kind: Literal["entidad", "hecho", "decision", "pendiente", "riesgo"] = Field(description="Tipo de atomo.")
    status: Literal["propuesto", "confirmado", "descartado"] = Field(default="propuesto", description="Revision humana.")
    source: str = Field(description="Id del documento fuente: Model:name.")
    source_field: str = Field(default="body", description="Campo del documento fuente donde vive el ancla.")
    start: int = Field(description="Offset inicial del ancla en el campo source_field.")
    end: int = Field(description="Offset final (exclusivo).")
    conf: float = Field(default=1.0, description="Confianza del extractor, 0 a 1.")
    tags: list[str] = Field(default_factory=list, description="Tags de grupo; los puntos dan jerarquia (infra.ingesta).")
    text: str = Field(description="El hecho, en una linea.")
    quote: str = Field(description="Cita literal del ancla; permite detectar drift.")


class InformeAvanceDoc(StructuredNLDoc):
    """Informe con cuatro slots fijos; cada slot lista rutas de atomos y guarda como se armo."""

    __compositions__ = {
        "resumen_txt": {"source_field": "resumen", "model": "models:AtomDoc", "template": "- {text}", "separator": "\n"},
        "decisiones_txt": {"source_field": "decisiones", "model": "models:AtomDoc", "template": "- {text}", "separator": "\n"},
        "riesgos_txt": {"source_field": "riesgos", "model": "models:AtomDoc", "template": "- {text}", "separator": "\n"},
        "pendientes_txt": {"source_field": "pendientes", "model": "models:AtomDoc", "template": "- {text}", "separator": "\n"},
    }
    __template__ = """
---
resumen: ⸢rev•resumen⸥
resumen_query: ⸢rev•resumen_query⸥
resumen_modo: ⸢rev•resumen_modo⸥
resumen_pins: ⸢rev•resumen_pins⸥
resumen_excluidos: ⸢rev•resumen_excluidos⸥
decisiones: ⸢rev•decisiones⸥
decisiones_query: ⸢rev•decisiones_query⸥
decisiones_modo: ⸢rev•decisiones_modo⸥
decisiones_pins: ⸢rev•decisiones_pins⸥
decisiones_excluidos: ⸢rev•decisiones_excluidos⸥
riesgos: ⸢rev•riesgos⸥
riesgos_query: ⸢rev•riesgos_query⸥
riesgos_modo: ⸢rev•riesgos_modo⸥
riesgos_pins: ⸢rev•riesgos_pins⸥
riesgos_excluidos: ⸢rev•riesgos_excluidos⸥
pendientes: ⸢rev•pendientes⸥
pendientes_query: ⸢rev•pendientes_query⸥
pendientes_modo: ⸢rev•pendientes_modo⸥
pendientes_pins: ⸢rev•pendientes_pins⸥
pendientes_excluidos: ⸢rev•pendientes_excluidos⸥
---

# ⸢rev•title⸥

## Resumen

⸢render•resumen_txt⸥

## Decisiones

⸢render•decisiones_txt⸥

## Riesgos

⸢render•riesgos_txt⸥

## Pendientes

⸢render•pendientes_txt⸥
""".strip()
    title: str = Field(description="Titulo del informe.")
    resumen: list[str] = Field(default_factory=list, description="Rutas de atomos del slot resumen.")
    resumen_query: str = Field(default="", description="Consulta que define el slot resumen.")
    resumen_pins: list[str] = Field(default_factory=list, description="Atomos fijados a mano en resumen.")
    resumen_excluidos: list[str] = Field(default_factory=list, description="Atomos excluidos de resumen.")
    resumen_modo: Literal["viñetas", "prosa", "tabla"] = Field(default="viñetas", description="Modo de presentacion de resumen.")

    decisiones: list[str] = Field(default_factory=list, description="Rutas de atomos del slot decisiones.")
    decisiones_query: str = Field(default="", description="Consulta que define el slot decisiones.")
    decisiones_pins: list[str] = Field(default_factory=list, description="Atomos fijados a mano en decisiones.")
    decisiones_excluidos: list[str] = Field(default_factory=list, description="Atomos excluidos de decisiones.")
    decisiones_modo: Literal["viñetas", "prosa", "tabla"] = Field(default="viñetas", description="Modo de presentacion de decisiones.")

    riesgos: list[str] = Field(default_factory=list, description="Rutas de atomos del slot riesgos.")
    riesgos_query: str = Field(default="", description="Consulta que define el slot riesgos.")
    riesgos_pins: list[str] = Field(default_factory=list, description="Atomos fijados a mano en riesgos.")
    riesgos_excluidos: list[str] = Field(default_factory=list, description="Atomos excluidos de riesgos.")
    riesgos_modo: Literal["viñetas", "prosa", "tabla"] = Field(default="viñetas", description="Modo de presentacion de riesgos.")

    pendientes: list[str] = Field(default_factory=list, description="Rutas de atomos del slot pendientes.")
    pendientes_query: str = Field(default="", description="Consulta que define el slot pendientes.")
    pendientes_pins: list[str] = Field(default_factory=list, description="Atomos fijados a mano en pendientes.")
    pendientes_excluidos: list[str] = Field(default_factory=list, description="Atomos excluidos de pendientes.")
    pendientes_modo: Literal["viñetas", "prosa", "tabla"] = Field(default="viñetas", description="Modo de presentacion de pendientes.")
