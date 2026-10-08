"""Instrucciones y mensaje de un turno: la variante que aplica y el contexto dinámico (spec 05 §6.6, §6.7)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.compile import CompiledAgent, InstructionVariant
from agents.segments import Profile, applies

LABELS = {
    "bundle": "Conocimiento relevante",
    "grounding": "Conocimiento relevante",
    "current_step": "Paso actual",
    "allowed_transitions": "Pasos a los que puedes ir",
    "profile": "Lo que sabemos de la persona",
    "records": "Datos de la persona",
    "open_events": "Pendientes",
    "summaries": "Conversaciones anteriores",
    "tool_result": "Resultado de la acción",
    "question": "Mensaje de la persona",
}
#: Todo lo que un agente puede pedir en `dynamic` (05 §6.6): los campos con etiqueta, el borrador
#: que entrega la etapa `gate` y la ventana de historial `history:<N>`.
DYNAMIC_FIELDS = (*LABELS, "draft", "history:<N>")


class Instructions(BaseModel, frozen=True):
    text: str = Field(description="Instrucciones finales del turno.")
    variant: str | None = Field(description="Ref de la variante usada; None si solo la base.")


def instructions_for(agent: CompiledAgent, profile: Profile) -> Instructions:
    """Base + la primera variante condicionada que aplica; la general ya va en la base."""
    chosen = _first_applicable(agent.instruction_variants, profile)
    if chosen is None:
        return Instructions(text=agent.instructions, variant=None)
    return Instructions(text=f"{agent.instructions}\n\n{chosen.text}", variant=chosen.ref)


def render_context(agent: CompiledAgent, context: dict[str, object]) -> str:
    """El mensaje del turno: una sección por campo dinámico declarado, la pregunta al final."""
    missing = [f for f in agent.dynamic_fields if f not in context]
    if missing:
        raise KeyError(f"{agent.role}: faltan campos dinámicos {missing}")
    fields = [f for f in agent.dynamic_fields if f != "question"] + ["question"] * (
        "question" in agent.dynamic_fields
    )
    return "\n\n".join(f"## {LABELS.get(f, f)}\n\n{_text(context[f])}" for f in fields if _text(context[f]))


def _first_applicable(variants: list[InstructionVariant], profile: Profile) -> InstructionVariant | None:
    return next((v for v in variants if v.applies_when and applies(v.applies_when, profile)), None)


def _text(value: object) -> str:
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value)  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, dict):
        return "\n".join(f"- {k}: {v}" for k, v in value.items())  # pyright: ignore[reportUnknownVariableType]
    return "" if value is None else str(value)
