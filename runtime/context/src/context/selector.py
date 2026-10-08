"""El compilador de contexto con LLM (spec 14 D7): un paso opcional del ruteador.

Corre sobre las mismas guardas de admisión que el ruteador heurístico: el modelo solo elige
dentro de lo admitido, y lo que el paso alcanza por relaciones declaradas entra siempre (lo
decidió quien escribió la KB). Si el modelo falla, el ruteador usa sus heurísticas.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from pydantic import BaseModel, Field
from pydantic_ai import Agent

log = logging.getLogger(__name__)

INSTRUCTIONS = (
    "Eliges qué documentos del conocimiento necesita un agente para responder este turno. "
    "Recibes el paso de la conversación, el mensaje de la persona y una lista de documentos, uno por "
    "línea como `ref — resumen`. Devuelve en `refs` solo las refs exactas de la lista que ayudan a "
    "responder; ninguna si ninguna ayuda. No inventes refs. `reason`: por qué, en una línea."
)


class ContextSelection(BaseModel, frozen=True):
    refs: list[str] = Field(description="Refs exactas de la lista que el agente necesita.")
    reason: str = Field(default="", description="Por qué, en una línea.")


class Selector(Protocol):
    def select(
        self, role: str, question: str, step: str | None, pool: list[tuple[str, str]]
    ) -> list[str] | None:
        """Las refs elegidas de `pool` (ref, resumen); None si no pudo elegir."""
        ...


class LlmSelector:
    def __init__(self, model: Any, settings: Any = None) -> None:
        self.model, self.settings = model, settings

    def select(
        self, role: str, question: str, step: str | None, pool: list[tuple[str, str]]
    ) -> list[str] | None:
        if not pool:
            return []
        agent = Agent(
            self.model, instructions=INSTRUCTIONS, output_type=ContextSelection, model_settings=self.settings
        )
        catalog = "\n".join(f"- {ref} — {summary}" for ref, summary in pool)
        sections = {
            "Agente": role,
            "Paso actual": step or "—",
            "Documentos": catalog,
            "Mensaje de la persona": question,
        }
        prompt = "\n\n".join(f"## {title}\n\n{body}" for title, body in sections.items())
        try:
            return list(agent.run_sync(prompt).output.refs)
        except Exception as exc:  # el turno sigue con las heurísticas
            log.warning("selector de contexto para %s falló: %s", role, exc)
            return None
