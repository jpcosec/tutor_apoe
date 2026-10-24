"""Evaluación de `applies_when` contra el perfil del turno (gramática cerrada de 01 §6.4)."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

_CONDITION = re.compile(r"^profile\.(?P<field>[a-z][a-z0-9_]*) (?P<op>==|!=|in) (?P<value>.+)$")


class Profile(BaseModel, frozen=True):
    """Lo que el turno sabe de la persona: su ficha (redactada) y sus rasgos asignados."""

    ficha: dict[str, object] = Field(default_factory=dict[str, object], description="Campos de la ficha.")
    traits: list[str] = Field(default_factory=list[str], description="Ids de rasgos asignados.")


def holds(condition: str, profile: Profile) -> bool:
    if condition.startswith("trait:"):
        return condition.removeprefix("trait:") in profile.traits
    match = _CONDITION.match(condition)
    if match is None:
        return False
    actual = profile.ficha.get(match["field"])
    value = match["value"]
    if match["op"] == "in":
        return str(actual) in [v.strip() for v in value.strip("[]").split(",")]
    return (str(actual) == value) == (match["op"] == "==")


def applies(conditions: list[str], profile: Profile) -> bool:
    return all(holds(c, profile) for c in conditions)
