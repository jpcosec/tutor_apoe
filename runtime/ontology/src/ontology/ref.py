"""`Ref`: referencia tipada a un objeto del sistema, con formato textual reversible (spec 13 §4.1)."""

from __future__ import annotations

import re
from typing import Literal, Self

from pydantic import BaseModel, model_validator

from ontology.grammar import IDENTIFIER_RE, MODEL_NAME_RE, first_invalid

Kind = Literal[
    "kb",
    "tool",
    "record",
    "subject",
    "turn",
    "conversation",
    "entity",
    "tool_call",
    "actor",
    "agent_run",
    "step_visit",
    "eval",
    # Familias canónicas de una sola componente (api-canonica §identidad).
    "machine_instance",
    "process_instance",
    "goal_instance",
    "self_assignment",
    "action_execution",
    "knowledge_activation",
    "knowledge_version",
    "observation",
    "receipt",
    "review_request",
    "delivery",
    "release",
    "deployment",
    "repair_case",
]

#: Cantidad de componentes de `id` por familia.
_COMPONENTS: dict[str, int] = {
    "kb": 2,
    "tool": 1,
    "record": 2,
    "subject": 1,
    "turn": 2,
    "conversation": 1,  # 14: el contexto de una conversación
    "entity": 1,  # 14: un tipo de registro de negocio
    "tool_call": 1,  # una llamada a tool, por su id
    "actor": 1,  # una persona del equipo (auditoría, cierre de casos)
    "agent_run": 3,  # <conversación>:<turno>:<rol>
    "step_visit": 2,  # <conversación>:<n>
    "eval": 1,  # una corrida de evals: dueña de sus sujetos sintéticos
    "machine_instance": 1,
    "process_instance": 1,
    "goal_instance": 1,
    "self_assignment": 1,
    "action_execution": 1,
    "knowledge_activation": 1,
    "knowledge_version": 1,
    "observation": 1,
    "receipt": 1,
    "review_request": 1,
    "delivery": 1,
    "release": 1,
    "deployment": 1,
    "repair_case": 1,
}


class RefFormatError(ValueError):
    """El texto no cumple la gramática de §4; `position` es el primer carácter inválido."""

    def __init__(self, text: str, position: int, reason: str) -> None:
        super().__init__(f"{reason} en {text!r}, posición {position}")
        self.text = text
        self.position = position
        self.reason = reason


class RefWithoutRelease(ValueError):
    """Una `Ref` de la KB que se va a persistir fuera de la KB no trae `release_id` (13 I3)."""


class Ref(BaseModel, frozen=True):
    """`<kind>:<id>[@<release_id>]`; `release_id` solo en la familia `kb`."""

    kind: Kind
    id: str
    release_id: str | None = None

    @model_validator(mode="after")
    def _grammar(self) -> Self:
        # Validar por el texto garantiza I5 por construcción: todo Ref que existe
        # se escribe y se vuelve a leer igual.
        _parse_parts(str(self))
        return self

    @classmethod
    def parse(cls, text: str) -> Ref:
        kind, ident, release_id = _parse_parts(text)
        return cls(kind=kind, id=ident, release_id=release_id)  # type: ignore[arg-type]

    def __str__(self) -> str:
        suffix = f"@{self.release_id}" if self.release_id is not None else ""
        return f"{self.kind}:{self.id}{suffix}"

    @property
    def parts(self) -> tuple[str, ...]:
        return tuple(self.id.split(":"))

    def require_release(self) -> Ref:
        if self.kind == "kb" and self.release_id is None:
            raise RefWithoutRelease(f"{self} se persiste fuera de la KB sin release_id")
        return self


def _parse_parts(text: str) -> tuple[str, str, str | None]:
    separator = text.find(":")
    if separator == -1:
        raise RefFormatError(text, len(text), "falta ':' después de la familia")
    kind = text[:separator]
    if kind not in _COMPONENTS:
        raise RefFormatError(text, 0, f"familia desconocida {kind!r}")

    body_start = separator + 1
    body = text[body_start:]
    at = body.find("@")
    if at == -1:
        ident, release_id = body, None
    elif kind != "kb":
        raise RefFormatError(text, body_start + at, "solo la familia kb admite @release_id")
    else:
        ident, release_id = body[:at], body[at + 1 :]
        _check(text, release_id, body_start + at + 1, "release_id", IDENTIFIER_RE)

    _check_components(text, kind, ident, body_start)
    return kind, ident, release_id


def _check_components(text: str, kind: str, ident: str, start: int) -> None:
    offset = start
    components = ident.split(":")
    for index, component in enumerate(components):
        is_model = kind == "kb" and index == 0
        pattern, what = (MODEL_NAME_RE, "nombre de modelo") if is_model else (IDENTIFIER_RE, "identificador")
        _check(text, component, offset, what, pattern)
        offset += len(component) + 1
    expected = _COMPONENTS[kind]
    if len(components) > expected:
        extra = start + len(":".join(components[:expected]))
        raise RefFormatError(text, extra, f"{kind} lleva {expected} componente(s) en id")
    if len(components) < expected:
        raise RefFormatError(text, start + len(ident), f"{kind} lleva {expected} componente(s) en id")


def _check(text: str, value: str, start: int, what: str, pattern: re.Pattern[str]) -> None:
    if not value:
        raise RefFormatError(text, start, f"{what} vacío")
    position = first_invalid(value, pattern)
    if position is not None:
        raise RefFormatError(text, start + position, f"carácter {value[position]!r} no permitido en {what}")
