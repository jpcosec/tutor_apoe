"""El ruteador de contexto: qué átomos tiene a la vista cada agente en cada turno (spec 14 §6.3, C1).

Cada agente consulta solo su porción de la KB (su `ProjectionDoc`). Los candidatos salen de la
semántica de la KB, con un motivo (`via`) cada uno, en orden de prioridad:

1. `step:<relación>`: lo que el paso actual alcanza por las relaciones que la proyección del rol lee.
2. `step:tag`: lo marcado con el tag del paso o con algo debajo de él en el DAG de sldb.
3. `profile`: lo que declara `applies_when` y aplica al perfil de la persona.
4. `semantic`: lo parecido a la pregunta, rankeado solo dentro de la porción del rol.

Con `select: llm` (14 D7), un modelo elige entre lo admitido en vez de las fuentes 2 a 4; lo que
el paso alcanza por relaciones declaradas entra igual (`selector.py`).

Entrar es un problema solo si trae contexto indeseado: las guardas de admisión lo impiden. Quedarse
no lo es. Salir cuando se necesita sí: un átomo sale solo si su motivo se invalida.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from agents import Profile, applies
from context.atoms import AtomEntry, LedgerEvent
from context.model import Context
from context.selector import Selector
from kb import Document, KnowledgeBase
from ontology import Ref

STEP_TAG_PREFIX = "conversation:steps."
TOOL_TAG = "type.knowledge.tool"
PRIORITY = {"step": 0, "profile": 1, "semantic": 2, "llm": 2, "read": 3}


class RoleRoute(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")
    semantic: bool = Field(default=True, description="Suma lo parecido a la pregunta dentro de la porción.")
    min_relevance: float = Field(default=0.2, description="Puntaje mínimo de la similitud.")
    select: Literal["heuristic", "llm"] = Field(
        default="heuristic", description="llm: un modelo elige entre lo admitido (14 D7)."
    )
    llm_pool: int = Field(
        default=30, ge=1, description="Cuántos admitidos ve el modelo, los heurísticos primero."
    )


class RouteContextConfig(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")
    roles: dict[str, RoleRoute] = Field(
        description="Rol de agents.yaml → ajustes; la porción es su proyección."
    )
    exclude_tags: list[str] = Field(
        default_factory=lambda: ["type.knowledge.gate"],
        description="Tags de modelo que nunca se rutean: los criterios del gate van después (C4).",
    )


class Candidate(BaseModel, frozen=True):
    key: str
    via: str
    score: float | None = None


class ContextRouter:
    """El único escritor de `active` y `ledger` para lo que viene de la KB (C1)."""

    def __init__(
        self,
        config: RouteContextConfig,
        kb: KnowledgeBase,
        projections: Mapping[str, str] | None = None,
        enabled_tools: list[str] | None = None,
        static: Mapping[str, list[str]] | None = None,
        selector: Selector | None = None,
    ) -> None:
        self.config, self.kb, self.selector = config, kb, selector
        self.projections = dict(projections or {})
        self.static = {role: set(refs) for role, refs in (static or {}).items()}
        self.enabled_tools = None if enabled_tools is None else set(enabled_tools)

    def route(self, context: Context) -> Context:
        for role in sorted(self.config.roles):
            entries, events = self._route_role(context, role, self.config.roles[role])
            context.active[role] = entries
            context.ledger.extend(events)
        return context

    def _route_role(
        self, context: Context, role: str, route: RoleRoute
    ) -> tuple[list[AtomEntry], list[LedgerEvent]]:
        visible = {d.key: d for d in self.kb.in_projection(self.projections.get(role, "all"))}
        fixed = self.static.get(role, set())  # ya va en sus instrucciones: rutearlo sería ruido
        admitted = {k: d for k, d in visible.items() if k not in fixed and self._admits(d, context.profile)}
        found = {c.key: c for c in self._candidates(context, role, route, admitted)}
        current = {e.key: e for e in context.active.get(role, [])}
        entries, events = self._merge(context, role, found, current)
        for key, entry in current.items():
            if key in found:
                continue
            reason = self._invalidated(entry, context, admitted)
            if reason is not None:
                events.append(_event(context.turn, role, entry.ref, "exit", reason, entry.content_hash))
                continue
            content_hash = admitted[key].content_hash
            if content_hash != entry.content_hash:  # retenido, pero su contenido cambió (C10)
                events.append(
                    _event(context.turn, role, entry.ref, "update", "content_changed", content_hash)
                )
                entry = entry.model_copy(update={"content_hash": content_hash})
            entries.append(entry)
        return sorted(entries, key=_order), events

    def _candidates(
        self, context: Context, role: str, route: RoleRoute, admitted: dict[str, Document]
    ) -> list[Candidate]:
        anchored = self._by_step_relations(context.current_step, role, admitted)
        heuristic = [
            *self._by_step_tag(context.current_step, admitted),
            *self._by_profile(context.profile, admitted),
            *(self._by_similarity(context.question, route, admitted) if route.semantic else []),
        ]
        if route.select == "llm" and self.selector is not None:
            chosen = _by_llm(self.selector, context, role, route, admitted, anchored, heuristic)
            heuristic = heuristic if chosen is None else chosen
        found: dict[str, Candidate] = {}
        for candidate in [*anchored, *heuristic]:
            found.setdefault(candidate.key, candidate)
        return list(found.values())

    def _by_step_relations(
        self, step: str | None, role: str, admitted: dict[str, Document]
    ) -> list[Candidate]:
        if step is None:
            return []
        relations = self.kb.projection(self.projections.get(role, "all")).relations
        return [
            Candidate(key=edge.target_ref, via=f"step:{relation}")
            for relation in relations
            for edge in self.kb.outgoing(step, relation)
            if edge.target_ref in admitted
        ]

    def _by_step_tag(self, step: str | None, admitted: dict[str, Document]) -> list[Candidate]:
        if step is None:
            return []
        tags = [t for t in self.kb.get(step).tags if t.startswith(STEP_TAG_PREFIX)]
        scope = {t for tag in tags for t in self.kb.tag_scope(tag)}
        return [
            Candidate(key=k, via="step:tag") for k, d in admitted.items() if scope & set(d.tags) and k != step
        ]

    def _by_profile(self, profile: Profile, admitted: dict[str, Document]) -> list[Candidate]:
        return [Candidate(key=k, via="profile") for k, d in admitted.items() if _conditions(d)]

    def _by_similarity(
        self, question: str, route: RoleRoute, admitted: dict[str, Document]
    ) -> list[Candidate]:
        if not question.strip() or not admitted:
            return []
        hits = self.kb.rank(question, k=len(admitted), threshold=route.min_relevance, among=list(admitted))
        return [Candidate(key=hit.ref, via="semantic", score=hit.score) for hit in hits]

    def _admits(self, document: Document, profile: Profile) -> bool:
        """Guardas de admisión: nada que traiga contexto indeseado (14 §6.3)."""
        if any(tag in document.model_tags for tag in self.config.exclude_tags):
            return False
        if not applies(_conditions(document), profile):  # de otro segmento
            return False
        return TOOL_TAG not in document.model_tags or self._enabled(document)

    def _enabled(self, document: Document) -> bool:
        """Una tool que el despliegue no habilitó no entra: el agente creería que existe."""
        return self.enabled_tools is None or tool_name(document) in self.enabled_tools

    def _merge(
        self, context: Context, role: str, found: dict[str, Candidate], current: dict[str, AtomEntry]
    ) -> tuple[list[AtomEntry], list[LedgerEvent]]:
        entries: list[AtomEntry] = []
        events: list[LedgerEvent] = []
        for key, candidate in found.items():
            previous, content_hash = current.get(key), self.kb.get(key).content_hash
            ref = Ref(kind="kb", id=key)
            if previous is None:
                events.append(_event(context.turn, role, ref, "enter", candidate.via, content_hash))
            elif previous.content_hash != content_hash:
                events.append(_event(context.turn, role, ref, "update", "content_changed", content_hash))
            entries.append(
                AtomEntry(
                    ref=ref,
                    reason=candidate.via,
                    score=candidate.score,
                    since_turn=previous.since_turn if previous else context.turn,
                    last_selected=context.turn,
                    content_hash=content_hash,
                )
            )
        return entries, events

    def _invalidated(self, entry: AtomEntry, context: Context, admitted: dict[str, Document]) -> str | None:
        """Un átomo sale solo si su motivo dejó de valer; lo parecido o leído se queda."""
        if entry.key not in admitted:
            return "inadmissible"
        if entry.reason.startswith("step:") and context.previous_step != context.current_step:
            return "step_change"
        if entry.reason == "profile":
            return "profile_change"
        return None


def _by_llm(
    selector: Selector,
    context: Context,
    role: str,
    route: RoleRoute,
    admitted: dict[str, Document],
    anchored: list[Candidate],
    heuristic: list[Candidate],
) -> list[Candidate] | None:
    """El modelo elige entre lo admitido que no trajo el paso; lo que elija fuera de ahí se ignora."""
    fixed = {c.key for c in anchored}
    ordered = [c.key for c in heuristic] + sorted(admitted)
    pool = list(dict.fromkeys(k for k in ordered if k not in fixed))[: route.llm_pool]
    refs = selector.select(
        role, context.question, context.current_step, [(k, _summary(admitted[k])) for k in pool]
    )
    if refs is None:
        return None
    allowed = set(pool)
    return [Candidate(key=ref, via="llm") for ref in dict.fromkeys(refs) if ref in allowed]


def _summary(document: Document) -> str:
    return str(document.payload.get("summary") or document.payload.get("title") or document.key)


def _conditions(document: Document) -> list[str]:
    raw = document.payload.get("applies_when")
    return [str(c) for c in cast(list[object], raw)] if isinstance(raw, list) else []


def tool_name(document: Document) -> str:
    """El nombre con que la LLM llama la tool: el de la operación o el de su declaración (03 §4.4)."""
    if document.payload.get("name"):
        return str(document.payload["name"])
    try:
        declared = json.loads(str(document.payload.get("parameters") or "{}"))
    except json.JSONDecodeError:
        return ""
    return str(declared.get("name") or "") if isinstance(declared, dict) else ""  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]


def _order(entry: AtomEntry) -> tuple[int, float, str]:
    """Por prioridad del motivo, después por puntaje descendente y, a igualdad, por clave (C3)."""
    return (PRIORITY.get(entry.reason.split(":")[0], 9), -(entry.score or 0.0), entry.key)


def _event(
    turn: int, role: str, ref: Ref, action: Literal["enter", "exit", "update"], reason: str, content_hash: str
) -> LedgerEvent:
    return LedgerEvent(turn=turn, role=role, ref=ref, action=action, reason=reason, content_hash=content_hash)
