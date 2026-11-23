"""Modelos del store demo del caso Levira: fuentes, atomos, informe por slots, publicacion y respuesta."""

from __future__ import annotations

import ast
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from sldb import StructuredNLDoc


class FuenteDoc(StructuredNLDoc):
    """Un texto fuente del caso (system prompt, folleto o mensaje). Los atomos lo anclan por offsets en `body`."""

    __semantics__ = {"type": ["knowledge", "source"]}
    __template__ = """
---
tipo: ⸢rev•tipo⸥
base: ⸢rev•base⸥
descripcion: ⸢rev•descripcion⸥
---

# ⸢rev•title⸥

⸢rev,markdown•body⸥
""".strip()
    title: str = Field(description="Titulo de la fuente.")
    tipo: Literal["prompt", "folleto", "mensaje"] = Field(description="Clase de fuente.")
    base: str = Field(description="Base a la que van los atomos de esta fuente (Programa o Paciente).")
    descripcion: str = Field(description="Una linea sobre que es la fuente.")
    body: str = Field(description="Texto fuente completo, parrafos separados por linea en blanco.")


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
    kind: Literal["regla", "criterio", "logistica", "paciente", "pregunta"] = Field(description="Tipo de atomo.")
    status: Literal["propuesto", "confirmado", "descartado"] = Field(default="propuesto", description="Revision humana.")
    source: str = Field(description="Id del documento fuente: Model:name.")
    source_field: str = Field(default="body", description="Campo del documento fuente donde vive el ancla.")
    start: int = Field(description="Offset inicial del ancla en el campo source_field.")
    end: int = Field(description="Offset final (exclusivo).")
    conf: float = Field(default=1.0, description="Confianza del extractor, 0 a 1.")
    tags: list[str] = Field(default_factory=list, description="Tags de grupo: base.subgrupo (programa.receta).")
    text: str = Field(description="El atomo, en una linea.")
    quote: str = Field(description="Cita literal del ancla; permite detectar drift.")


class SalidaDoc(StructuredNLDoc):
    """Informe del caso con cuatro slots fijos; cada slot lista rutas de atomos y guarda como se armo."""

    __compositions__ = {
        "respuesta_txt": {"source_field": "respuesta", "model": "models:AtomDoc", "template": "- {text}", "separator": "\n"},
        "acceso_txt": {"source_field": "acceso", "model": "models:AtomDoc", "template": "- {text}", "separator": "\n"},
        "cercanos_txt": {"source_field": "cercanos", "model": "models:AtomDoc", "template": "- {text}", "separator": "\n"},
        "reglas_txt": {"source_field": "reglas", "model": "models:AtomDoc", "template": "- {text}", "separator": "\n"},
    }
    __template__ = """
---
respuesta: ⸢rev•respuesta⸥
respuesta_titulo: ⸢rev•respuesta_titulo⸥
respuesta_rotulo: ⸢rev•respuesta_rotulo⸥
respuesta_query: ⸢rev•respuesta_query⸥
respuesta_modo: ⸢rev•respuesta_modo⸥
respuesta_pins: ⸢rev•respuesta_pins⸥
respuesta_excluidos: ⸢rev•respuesta_excluidos⸥
acceso: ⸢rev•acceso⸥
acceso_titulo: ⸢rev•acceso_titulo⸥
acceso_rotulo: ⸢rev•acceso_rotulo⸥
acceso_query: ⸢rev•acceso_query⸥
acceso_modo: ⸢rev•acceso_modo⸥
acceso_pins: ⸢rev•acceso_pins⸥
acceso_excluidos: ⸢rev•acceso_excluidos⸥
cercanos: ⸢rev•cercanos⸥
cercanos_titulo: ⸢rev•cercanos_titulo⸥
cercanos_rotulo: ⸢rev•cercanos_rotulo⸥
cercanos_query: ⸢rev•cercanos_query⸥
cercanos_modo: ⸢rev•cercanos_modo⸥
cercanos_pins: ⸢rev•cercanos_pins⸥
cercanos_excluidos: ⸢rev•cercanos_excluidos⸥
reglas: ⸢rev•reglas⸥
reglas_titulo: ⸢rev•reglas_titulo⸥
reglas_rotulo: ⸢rev•reglas_rotulo⸥
reglas_query: ⸢rev•reglas_query⸥
reglas_modo: ⸢rev•reglas_modo⸥
reglas_pins: ⸢rev•reglas_pins⸥
reglas_excluidos: ⸢rev•reglas_excluidos⸥
---

# ⸢rev•title⸥

## Respuesta al paciente

⸢render•respuesta_txt⸥

## Acceso a receta

⸢render•acceso_txt⸥

## Puntos cercanos

⸢render•cercanos_txt⸥

## Reglas aplicadas

⸢render•reglas_txt⸥
""".strip()
    title: str = Field(description="Titulo del informe.")

    respuesta: list[str] = Field(default_factory=list, description="Rutas de atomos del slot respuesta (la lista persistida).")
    respuesta_titulo: str = Field(default="Respuesta al paciente", description="Titulo de la seccion del slot respuesta.")
    respuesta_rotulo: str = Field(default="", description="Rotulo del slot respuesta.")
    respuesta_query: str = Field(default="", description="Consulta (chips y texto libre) que define el slot respuesta.")
    respuesta_modo: Literal["viñetas", "prosa", "tabla"] = Field(default="viñetas", description="Modo de presentacion de respuesta.")
    respuesta_pins: list[str] = Field(default_factory=list, description="Atomos fijados a mano en respuesta.")
    respuesta_excluidos: list[str] = Field(default_factory=list, description="Atomos excluidos de respuesta.")

    acceso: list[str] = Field(default_factory=list, description="Rutas de atomos del slot acceso (la lista persistida).")
    acceso_titulo: str = Field(default="Acceso a receta", description="Titulo de la seccion del slot acceso.")
    acceso_rotulo: str = Field(default="", description="Rotulo del slot acceso.")
    acceso_query: str = Field(default="", description="Consulta (chips y texto libre) que define el slot acceso.")
    acceso_modo: Literal["viñetas", "prosa", "tabla"] = Field(default="viñetas", description="Modo de presentacion de acceso.")
    acceso_pins: list[str] = Field(default_factory=list, description="Atomos fijados a mano en acceso.")
    acceso_excluidos: list[str] = Field(default_factory=list, description="Atomos excluidos de acceso.")

    cercanos: list[str] = Field(default_factory=list, description="Rutas de atomos del slot cercanos (la lista persistida).")
    cercanos_titulo: str = Field(default="Puntos cercanos", description="Titulo de la seccion del slot cercanos.")
    cercanos_rotulo: str = Field(default="", description="Rotulo del slot cercanos.")
    cercanos_query: str = Field(default="", description="Consulta (chips y texto libre) que define el slot cercanos.")
    cercanos_modo: Literal["viñetas", "prosa", "tabla"] = Field(default="viñetas", description="Modo de presentacion de cercanos.")
    cercanos_pins: list[str] = Field(default_factory=list, description="Atomos fijados a mano en cercanos.")
    cercanos_excluidos: list[str] = Field(default_factory=list, description="Atomos excluidos de cercanos.")

    reglas: list[str] = Field(default_factory=list, description="Rutas de atomos del slot reglas (la lista persistida).")
    reglas_titulo: str = Field(default="Reglas aplicadas", description="Titulo de la seccion del slot reglas.")
    reglas_rotulo: str = Field(default="", description="Rotulo del slot reglas.")
    reglas_query: str = Field(default="", description="Consulta (chips y texto libre) que define el slot reglas.")
    reglas_modo: Literal["viñetas", "prosa", "tabla"] = Field(default="viñetas", description="Modo de presentacion de reglas.")
    reglas_pins: list[str] = Field(default_factory=list, description="Atomos fijados a mano en reglas.")
    reglas_excluidos: list[str] = Field(default_factory=list, description="Atomos excluidos de reglas.")


class PublicacionDoc(StructuredNLDoc):
    """Foto inmutable del informe (un documento por version, no se edita). Una seccion por slot, en markdown.

    Secciones separadas y no un unico `body`: SLDB rechaza headings dentro de un field y un field `markdown`
    con headings no sobrevive al round-trip; `rev,markdown` si conserva viñetas y parrafos.
    """

    __semantics__ = {"type": ["knowledge", "publication"]}
    __template__ = """
---
informe: ⸢rev•informe⸥
version: ⸢rev•version⸥
atoms: ⸢rev•atoms⸥
---

# ⸢rev•title⸥

## Respuesta al paciente

⸢rev,markdown•respuesta⸥

## Acceso a receta

⸢rev,markdown•acceso⸥

## Puntos cercanos

⸢rev,markdown•cercanos⸥

## Reglas aplicadas

⸢rev,markdown•reglas⸥
""".strip()
    informe: str = Field(description="Id del informe publicado.")
    version: int = Field(description="Numero de version, correlativo por informe.")
    atoms: list[str] = Field(default_factory=list, description="Rutas de los atomos incluidos en la foto.")
    title: str = Field(description="Titulo del informe al publicar.")
    respuesta: str = Field(default="", description="Seccion Respuesta al paciente tal como la renderiza SLDB.")
    acceso: str = Field(default="", description="Seccion Acceso a receta tal como la renderiza SLDB.")
    cercanos: str = Field(default="", description="Seccion Puntos cercanos tal como la renderiza SLDB.")
    reglas: str = Field(default="", description="Seccion Reglas aplicadas tal como la renderiza SLDB.")


class Frase(BaseModel):
    """Una frase de la respuesta y los atomos de los que sale."""

    texto: str = Field(description="Texto de la frase.")
    atomos: list[str] = Field(default_factory=list, description="Ids de los atomos de esta frase, en orden.")

    @field_validator("atomos", mode="before")
    @classmethod
    def _celda_a_lista(cls, v):
        """La tabla markdown guarda la celda como texto ("['c5', 'c3']" o "c5, c3"); se relee como lista."""
        if isinstance(v, str):
            t = v.strip()
            if t.startswith("["):
                return [str(x) for x in ast.literal_eval(t)]
            return [x.strip() for x in t.split(",") if x.strip()]
        return v


class RespuestaDoc(StructuredNLDoc):
    """La respuesta al paciente: texto completo y, por frase, los atomos que la respaldan."""

    __semantics__ = {"type": ["knowledge", "response"]}
    __template__ = """
---
caso: ⸢rev•caso⸥
proyecto: ⸢rev•proyecto⸥
estado: ⸢rev•estado⸥
generada_por: ⸢rev•generada_por⸥
slot: ⸢rev•slot⸥
mensaje: ⸢rev•mensaje⸥
---

# ⸢rev•title⸥

⸢rev,markdown•respuesta⸥

## Frases

⸢rev,table•frases⸥
""".strip()
    title: str = Field(description="Titulo de la vista de respuesta.")
    caso: str = Field(description="Id del caso (caso-0217).")
    proyecto: str = Field(default="", description="Proyecto al que pertenece el caso (levira-contigo); se ve en la cabecera de la maqueta.")
    estado: str = Field(default="borrador", description="Estado de la respuesta: borrador o enviada.")
    generada_por: str = Field(description="De donde sale el texto (modelo o persona).")
    slot: str = Field(description="Slot del informe del que sale la respuesta.")
    mensaje: str = Field(description="Id del FuenteDoc del mensaje al que responde.")
    respuesta: str = Field(description="Texto completo de la respuesta: las frases unidas con un espacio.")
    frases: list[Frase] = Field(default_factory=list, description="Frases de la respuesta con sus atomos.")
