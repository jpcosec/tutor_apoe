"""La declaración de agentes (spec 05 §4, spec 16): qué agentes hay y qué contexto ven.

Viene de los `AgentDoc` de la KB o, como respaldo, de `agents.yaml`. Un agente no tiene tipo:
lo que hace lo definen su esquema de salida y la etapa que lo usa. Cada sección fija de sus
instrucciones nombra el tag de la KB de donde sale y su título; el código no guarda esa tabla.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

Render = Literal["documents", "cited", "framing", "step_graph"]
#: Políticas opcionales de 05 §6.5. `transition_guard` corre siempre en `decide` y `respond`
#: (06 I3); validar los argumentos de las tools lo hace Pydantic AI.
Policy = Literal["deny_if_no_context"]


class StaticSection(BaseModel, frozen=True):
    """Una sección fija de las instrucciones: los documentos de la KB con ese tag."""

    model_config = ConfigDict(extra="forbid")
    tag: str = Field(
        pattern=r"^[a-z0-9_.-]+$", description="Tag de modelo de la KB (ej. type.knowledge.self)."
    )
    title: str = Field(description="Título de la sección en las instrucciones.")
    render: Render = Field(
        default="documents",
        description=(
            "documents: el cuerpo de cada documento (los que traen `applies_when` son variantes); "
            "cited: igual, con título y ref de cada uno para que el agente los nombre; "
            "framing: solo los del rol del agente; step_graph: los pasos con sus transiciones."
        ),
    )


class ContextDecl(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")
    static: list[StaticSection] = Field(
        default_factory=list[StaticSection], description="Resueltos al compilar, desde la KB."
    )
    dynamic: list[str] = Field(default_factory=list[str], description="Los llena 06 en cada turno.")


class AgentDecl(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", description="Rol único (identificador, 13 §4.0).")
    framing: str = Field(default="", description="Quién es este agente en este negocio (el AgentDoc).")
    output_schema: str | None = Field(default=None, description="Esquema versionado de la salida.")
    projection: str = Field(default="all", description="ProjectionDoc de la KB (D11).")
    context: ContextDecl = Field(default_factory=ContextDecl, description="Contexto estático y dinámico.")
    tools: list[str] = Field(default_factory=list[str], description="Tools de lectura de KB.")
    business_tools: list[str] | None = Field(
        default=None,
        description="Tools de negocio que puede llamar (pendientes F2); None = las de siempre: todas "
        "las habilitadas si es el agente de `decide`, ninguna si no.",
    )
    on_failure: Literal["open", "closed"] = Field(description="Qué devuelve si el modelo falla (I5).")
    model: str | None = Field(default=None, description="Par propio; None = el del despliegue.")
    max_tool_iterations: int = Field(default=4, description="Tope del bucle modelo→tool→modelo.")
    policies: list[Policy] = Field(default_factory=list[Policy], description="Políticas (05 §6.5), en orden.")
    evidence: Literal["auto", "off"] = Field(
        default="auto", description="Con un esquema que trae claims: auto exige evidence_gate en la cadena."
    )


class AgentsDeclaration(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")
    capabilities_version: int = Field(default=2, description="Versión del catálogo.")
    agents: list[AgentDecl] = Field(description="Los agentes del cliente.")

    def get(self, role: str) -> AgentDecl:
        return next(a for a in self.agents if a.role == role)


def load_agents(path: Path) -> AgentsDeclaration:
    return AgentsDeclaration.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
