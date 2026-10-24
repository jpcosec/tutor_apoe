"""Lo que queda disponible de un turno cerrado (spec 14 §6.1)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TurnSummary(BaseModel, frozen=True):
    turn: int
    question: str
    step_before: str | None
    step_after: str | None
    decision: str | None = Field(default=None, description="kind de TurnDecision.")
    tool: dict[str, object] | None = Field(default=None, description="ToolOutcome.for_model() de 03.")

    def line(self) -> str:
        """Una línea para el campo dinámico `trace` (14 §6.4)."""
        tool = f", tool {self.tool.get('tool')} → {self.tool.get('status')}" if self.tool else ""
        step = f"{self.step_before or '—'} → {self.step_after or '—'}"
        return f"turno {self.turn}: «{self.question}» ({step}, {self.decision or 'sin decisión'}{tool})"
