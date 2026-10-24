"""Átomos activos por rol y el ledger que los reproduce (spec 14 §6.1, C2)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from ontology import Ref


class AtomEntry(BaseModel, frozen=True):
    ref: Ref = Field(description="kb:<Modelo>:<nombre>.")
    reason: str = Field(description="Estrategia que lo trajo.")
    score: float | None = Field(default=None, description="Puntaje, si la estrategia lo da.")
    since_turn: int = Field(description="Turno en que entró.")
    last_selected: int = Field(description="Último turno en que el ruteador lo volvió a elegir.")
    content_hash: str = Field(default="", description="Huella del contenido que vio el agente (01, de sldb).")

    @property
    def key(self) -> str:
        """`Modelo:nombre`, la clave del documento en la KB."""
        return self.ref.id


class LedgerEvent(BaseModel, frozen=True):
    turn: int
    role: str
    ref: Ref
    action: Literal["enter", "exit", "update"]
    reason: str = Field(
        description="enter: motivo (via); exit: step_change | profile_change | inadmissible; "
        "update: content_changed."
    )
    content_hash: str = Field(default="", description="Huella del contenido del átomo en ese turno.")


def replay_active(ledger: Sequence[LedgerEvent]) -> dict[str, list[Ref]]:
    """El conjunto activo que resulta de aplicar el ledger en orden (C2), por rol y orden de entrada."""
    active: dict[str, dict[Ref, None]] = {}
    for event in ledger:
        refs = active.setdefault(event.role, {})
        if event.action == "enter":
            refs[event.ref] = None
        elif event.action == "exit":
            refs.pop(event.ref, None)
    return {role: list(refs) for role, refs in active.items() if refs}
