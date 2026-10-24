"""El documento que gobierna el rol del tutor (adaptado de `AgentDoc` del esquema de referencia).

Tag semántico `type.governance.agent`: `kb` lo excluye de toda proyección y del índice;
lo cambian personas, no agentes. Declara quién es el tutor (`framing`, de persona.md), qué
normas sigue al responder (`instructions`, de prompt_policy.md) y qué proyección de la KB ve.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sldb import StructuredNLDoc

from .apos import AtomTag


class StaticSection(BaseModel):
    """Una sección fija de las instrucciones del agente: los documentos con ese tag."""

    tag: str = Field(description="Tag de modelo de la KB (ej. type.knowledge.atom).")
    title: str = Field(description="Título de la sección en las instrucciones.")
    render: Literal["documents", "cited", "framing", "step_graph"] = Field(
        default="documents", description="Cómo se renderizan los documentos de la sección."
    )


class AgentDoc(StructuredNLDoc):
    """Un agente del runtime: su encuadre, sus normas, lo que ve y cómo falla."""

    __family__ = "agent"
    __semantics__ = {"type": ["governance", "agent"], "workspace": ["knowledge"]}
    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
role: ⸢rev•role⸥
projection: ⸢rev•projection⸥
static: ⸢rev•static⸥
dynamic: ⸢rev•dynamic⸥
tools: ⸢rev•tools⸥
on_failure: ⸢rev•on_failure⸥
policies: ⸢rev•policies⸥
tags: ⸢rev•tags⸥
provenance: ⸢optrev•provenance⸥
summary: ⸢rev•summary⸥
---

# ⸢render•title⸥

## Framing

⸢rev•framing⸥

## Instructions

⸢rev•instructions⸥
""".strip()

    id: str = Field(description="Identificador estable, por convención 'agent-<rol>'.")
    title: str = Field(description="Nombre legible del agente.")
    role: str = Field(description="Rol con que lo nombra el runtime (ej. tutor).")
    framing: str = Field(description="Quién es este agente y qué hace (la persona).")
    instructions: str = Field(description="Normas que sigue al responder (la política de prompt).")
    projection: str = Field(default="all", description="ProjectionDoc que define su porción de la KB.")
    static: list[StaticSection] = Field(default_factory=list, description="Secciones fijas de sus instrucciones.")
    dynamic: list[str] = Field(default_factory=list, description="Campos que el turno le entrega.")
    tools: list[str] = Field(default_factory=list, description="Tools de lectura de su porción de la KB.")
    on_failure: Literal["open", "closed"] = Field(default="closed", description="Qué devuelve si el modelo falla.")
    policies: list[Literal["deny_if_no_context"]] = Field(
        default_factory=list, description="Políticas deterministas del runtime, en orden."
    )
    tags: list[AtomTag] = Field(default_factory=list, description="Tags editoriales (agent:<rol>).")
    provenance: str | None = Field(default=None, description="De dónde sale la declaración.")
    summary: str = Field(description="Una línea: qué hace este agente.")
