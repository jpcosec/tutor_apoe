"""Lo que un rol ve del contexto: función pura de contexto, agente y ontología (spec 14 §6.4, C3).

Todo lo que no es un átomo de la KB se renderiza con las vistas de la ontología (15 O1).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from typing import cast

from pydantic import BaseModel, Field

from agents import CompiledAgent, body_of, render_context
from context.model import Context
from semantics import Ontology

Source = Callable[[Context, str, Ontology, int], object]


class Projection(BaseModel, frozen=True):
    role: str
    fields: dict[str, object] = Field(description="Campos dinámicos para el runner del agente.")
    text: str = Field(description="El mensaje del turno renderizado.")
    sha256: str = Field(description="Huella del texto; va a la traza (C3).")


def project(
    context: Context,
    agent: CompiledAgent,
    ontology: Ontology,
    extras: Mapping[str, object] | None = None,
    trace_window: int = 5,
) -> Projection:
    """`extras` trae lo que es del turno y no del contexto: el resultado de la tool, las declaraciones."""
    given = {name: _rendered(name, value, ontology) for name, value in (extras or {}).items()}
    fields = {
        name: given[name] if name in given else _source(name)(context, agent.role, ontology, trace_window)
        for name in agent.dynamic_fields
    }
    text = render_context(agent, fields)
    return Projection(
        role=agent.role, fields=fields, text=text, sha256=hashlib.sha256(text.encode()).hexdigest()
    )


def _rendered(name: str, value: object, ontology: Ontology) -> object:
    """Los resultados de las tools llegan crudos y cada uno se renderiza con su vista (15 §6.1)."""
    if name != "tool_result":
        return value
    outcomes = cast(list[object], value) if isinstance(value, list) else [value]
    rendered = [
        ontology.render_tool_result(cast(dict[str, object], outcome))
        for outcome in outcomes
        if isinstance(outcome, dict)
    ]
    return "\n\n".join(rendered) or None


def _source(name: str) -> Source:
    try:
        return SOURCES[name]
    except KeyError as error:
        raise KeyError(f"el campo dinámico {name!r} no sale del contexto ni vino en extras") from error


def _atoms(context: Context, role: str, ontology: Ontology, _: int) -> list[str]:
    kb = ontology.kb
    return [f"[{e.key}]\n{body_of(kb, kb.get(e.key))}" for e in context.active.get(role, [])]


def _transitions(context: Context, _: str, ontology: Ontology, __: int) -> list[str]:
    step = context.current_step
    return [r.target_ref for r in ontology.kb.outgoing(step, "transitions_to")] if step else []


def _trace(context: Context, _: str, ontology: Ontology, window: int) -> str:
    return ontology.render_trace(context.trace[-window:]) if window else ""


def _step(context: Context, _: str, __: Ontology, ___: int) -> object:
    return context.current_step


def _profile(context: Context, _: str, ontology: Ontology, ___: int) -> object:
    return ontology.render_profile(context.profile.ficha)


def _question(context: Context, _: str, __: Ontology, ___: int) -> object:
    return context.question


def _summaries(context: Context, _: str, __: Ontology, ___: int) -> object:
    """La memoria entre conversaciones: lo que se resumió al cerrar las anteriores (08 §6.8)."""
    return list(context.summaries)


def _none(context: Context, _: str, __: Ontology, ___: int) -> object:
    """Lo del turno en curso (resultado de la tool) llega por `extras`; sin él, no hay nada."""
    return None


SOURCES: dict[str, Source] = {
    "bundle": _atoms,
    "grounding": _atoms,
    "current_step": _step,
    "allowed_transitions": _transitions,
    "profile": _profile,
    "trace": _trace,
    "tool_result": _none,
    "summaries": _summaries,
    "question": _question,
}
