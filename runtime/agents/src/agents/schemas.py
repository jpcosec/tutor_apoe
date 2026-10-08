"""Esquemas de salida versionados (spec 05 §6.4), en lo que la rebanada usa."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ToolCallRequest(BaseModel, frozen=True):
    """Una llamada a tool que hizo el agente en su corrida (la ejecuta Pydantic AI, no el turno)."""

    name: str = Field(description="Nombre de la tool.")
    arguments: dict[str, object] = Field(default_factory=dict[str, object], description="Argumentos.")


class TurnDecision(BaseModel, frozen=True):
    """`TurnDecision@1`: cómo sigue el turno después de las tools que el decisor ya llamó."""

    kind: Literal["nl", "fallback"] = Field(description="Responder o no entender.")
    step_target: str | None = Field(
        default=None, description="Paso al que va la conversación (Modelo:nombre)."
    )
    reason: str = Field(default="", description="Por qué, en una línea.")

    @classmethod
    def fallback(cls) -> TurnDecision:
        return cls(kind="fallback")


class Claim(BaseModel, frozen=True):
    span: str = Field(description="El fragmento exacto del texto que afirma algo del dominio.")
    refs: list[str] = Field(
        min_length=1, description="De dónde sale: kb:Modelo:nombre o record:<entidad>:<clave>."
    )


class DraftWithEvidence(BaseModel, frozen=True):
    """`DraftWithEvidence@1` (05 §6.4): la respuesta y sus afirmaciones de dominio con respaldo."""

    text: str = Field(description="La respuesta que se envía a la persona.")
    claims: list[Claim] = Field(default_factory=list[Claim], description="Una por afirmación de dominio.")


class Respond(DraftWithEvidence, frozen=True):
    """`Respond@1` (spec 16): un agente de una sola llamada redacta y decide el paso siguiente."""

    step_target: str | None = Field(
        default=None, description="Paso al que va la conversación (Modelo:nombre); null si se queda."
    )


class Violation(BaseModel, frozen=True):
    criterion_ref: str = Field(description="El criterio que rompe (Modelo:nombre).")
    span: str = Field(description="El fragmento exacto del borrador que lo rompe.")
    reason: str = Field(default="", description="Por qué, en una línea.")

    @property
    def criterion(self) -> str:
        """El id del criterio: `[GateCriterion:gate-x]` o `gate-x` son `gate-x`."""
        return self.criterion_ref.strip("[]` ").rpartition(":")[2]

    def quotes(self, draft: str) -> bool:
        """¿El fragmento está en el borrador? Sin distinguir espacios ni mayúsculas."""
        span = " ".join(self.span.strip("\"'«»“” ").split()).casefold()
        return bool(span) and span in " ".join(draft.split()).casefold()


class GateVerdict(BaseModel, frozen=True):
    """`GateVerdict@1` (05 §6.4, 06 §6.2 `gate`): el borrador cumple los criterios o no sale.

    Cada rechazo cita el fragmento del borrador que rompe el criterio; la etapa descarta los que
    no están en el borrador (un criterio no se rompe por omisión). Deciden las violaciones
    citadas; un `approved: false` sin ninguna también rechaza (un rechazo sin motivo no es una
    aprobación)."""

    approved: bool = Field(description="True si el borrador cumple todos los criterios.")
    violations: list[Violation] = Field(
        default_factory=list[Violation], description="Una por criterio roto; vacío si aprueba."
    )

    @classmethod
    def fallback(cls) -> GateVerdict:
        """Sin veredicto no hay aprobación: un revisor que falla no deja pasar el borrador (I5)."""
        return cls(approved=False)


SCHEMAS: dict[str, type[BaseModel]] = {
    "TurnDecision@1": TurnDecision,
    "GateVerdict@1": GateVerdict,
    "DraftWithEvidence@1": DraftWithEvidence,
    "Respond@1": Respond,
}

#: Los esquemas cuya salida trae afirmaciones citadas: las revisa `evidence_gate` (06 D12).
WITH_CLAIMS = frozenset({"DraftWithEvidence@1", "Respond@1"})
