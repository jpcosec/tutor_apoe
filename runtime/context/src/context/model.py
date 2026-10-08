"""`Context`: lo que el flujo agéntico necesita para operar en una conversación (spec 14 §6.1)."""

from __future__ import annotations

from pydantic import Field

from agents import HistoryMessage, Profile
from context.atoms import AtomEntry, LedgerEvent
from context.episodes import StepVisit
from context.summary import TurnSummary
from ontology import OntologyObject, Ref
from tools import STATE_PREFIX


class Context(OntologyObject):
    schema_version: int = 1
    session_id: str = Field(description="El sujeto, pseudónimo, que resolvió el canal.")
    conversation_id: str | None = Field(
        default=None, description="La conversación de 02; nace y muere con ella."
    )
    turn: int = Field(default=0, description="0 antes del primer turno.")
    fingerprint: str = Field(default="", description="Huella de la ontología en este turno (15 O3, 14 C10).")
    subject: str | None = Field(default=None, description="Sujeto pseudónimo, si se resolvió.")
    profile: Profile = Field(default_factory=Profile)
    question: str = ""
    current_step: str | None = None
    history: list[HistoryMessage] = Field(default_factory=list[HistoryMessage])
    summaries: list[str] = Field(
        default_factory=list[str],
        description="Resúmenes de las conversaciones anteriores del sujeto, fijados al abrir esta (06 §6.4).",
    )
    trace: list[TurnSummary] = Field(default_factory=list[TurnSummary])
    active: dict[str, list[AtomEntry]] = Field(default_factory=dict[str, list[AtomEntry]])
    ledger: list[LedgerEvent] = Field(default_factory=list[LedgerEvent])
    step_visits: list[StepVisit] = Field(
        default_factory=list[StepVisit], description="Los pasos por los que pasó la conversación."
    )
    transcripts: dict[str, list[dict[str, object]]] = Field(
        default_factory=dict[str, list[dict[str, object]]],
        description="Por rol, los mensajes de Pydantic AI de este turno (payload opaco); los de turnos "
        "anteriores quedan en sus fotos (14 §6.5).",
    )
    state: dict[str, object] = Field(
        default_factory=dict[str, object],
        description="Identificadores del flujo que leen los bindings; nunca texto personal (14 C6).",
    )

    @classmethod
    def new(cls, session_id: str, conversation_id: str | None = None) -> Context:
        """Un contexto vacío para una conversación nueva: turno 0, sin traza ni átomos."""
        ref = Ref(kind="conversation", id=conversation_id or session_id)
        return cls(ref=ref, session_id=session_id, conversation_id=conversation_id)

    def open_turn(self, question: str, step: str | None) -> None:
        """Empieza un turno: sube el contador y vacía lo que es de un solo turno."""
        self.turn += 1
        self.question, self.current_step, self.transcripts = question, step, {}

    @property
    def previous_step(self) -> str | None:
        """El paso en que corrió el turno anterior, cuyo grounding sigue activo; None en el primero."""
        return self.trace[-1].step_before if self.trace else None

    def bindings(self) -> dict[str, object]:
        """Lo que una tool de alto nivel puede recibir sin que lo aporte la LLM (C6)."""
        fixed: dict[str, object] = {
            "context.subject": self.subject or self.session_id,
            "context.session": self.session_id,
            "context.step": self.current_step,
        }
        return fixed | {f"{STATE_PREFIX}{key}": value for key, value in self.state.items()}

    def append_transcript(self, role: str, messages: list[dict[str, object]]) -> None:
        self.transcripts.setdefault(role, []).extend(messages)

    def admit_read(self, role: str, key: str, content_hash: str) -> None:
        """Lo que el agente leyó de su porción entra a su contexto (`read`) y se queda (14 §6.3)."""
        entries = self.active.setdefault(role, [])
        if any(entry.key == key for entry in entries):
            return
        ref = Ref(kind="kb", id=key)
        entries.append(
            AtomEntry(
                ref=ref,
                reason="read",
                since_turn=self.turn,
                last_selected=self.turn,
                content_hash=content_hash,
            )
        )
        self.ledger.append(
            LedgerEvent(
                turn=self.turn, role=role, ref=ref, action="enter", reason="read", content_hash=content_hash
            )
        )
