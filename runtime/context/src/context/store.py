"""Persistencia del contexto como puerto (spec 14 §7): una foto por turno, con el ledger dentro (D1)."""

from __future__ import annotations

from typing import Protocol

from context.model import Context

#: Texto de la persona o de las tools: el almacén lo anonimiza (C5). `state` no va aquí:
#: guarda identificadores que leen los bindings, y un marcador en su lugar los rompería.
PERSONAL = frozenset({"question", "trace", "transcripts", "summaries"})
#: No se guarda: el historial ya vive en su tabla (02) y `compile_context` lo recarga.
NOT_STORED = frozenset({"history"})


class ContextStore(Protocol):
    """Lo cumplen `InMemoryContextStore` y el `SqlStore` de 02; `personal` va anonimizado.

    Con `conversation_id`, la foto es la de esa conversación; sin él, la última del sujeto.
    """

    def load_context(
        self, session_id: str, conversation_id: str | None = None
    ) -> dict[str, object] | None: ...
    def save_context(
        self,
        session_id: str,
        turn: int,
        public: dict[str, object],
        personal: dict[str, object],
        conversation_id: str | None = None,
    ) -> None: ...


class InMemoryContextStore:
    def __init__(self) -> None:
        self._contexts: dict[tuple[str, str | None], dict[str, object]] = {}
        self._latest: dict[str, dict[str, object]] = {}

    def load_context(self, session_id: str, conversation_id: str | None = None) -> dict[str, object] | None:
        if conversation_id is None:
            return self._latest.get(session_id)
        return self._contexts.get((session_id, conversation_id))

    def save_context(
        self,
        session_id: str,
        turn: int,
        public: dict[str, object],
        personal: dict[str, object],
        conversation_id: str | None = None,
    ) -> None:
        self._contexts[(session_id, conversation_id)] = self._latest[session_id] = public | personal


def load(store: ContextStore, session_id: str, conversation_id: str | None = None) -> Context:
    """El contexto de la conversación; una conversación nueva empieza de cero (14 §6.1)."""
    raw = store.load_context(session_id, conversation_id)
    return Context.model_validate(raw) if raw is not None else Context.new(session_id, conversation_id)


def save(store: ContextStore, context: Context) -> None:
    data = {k: v for k, v in context.model_dump(mode="json").items() if k not in NOT_STORED}
    public = {k: v for k, v in data.items() if k not in PERSONAL}
    personal = {k: v for k, v in data.items() if k in PERSONAL}
    store.save_context(context.session_id, context.turn, public, personal, context.conversation_id)
