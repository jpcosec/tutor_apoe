"""El tutor APOS como agente de pydantic-ai sobre los módulos vendoreados.

Un turno tiene dos mitades, y las dos quedan auditables en `TurnResult`:

1. La *mesa* (`build_context`): qué átomos de la KB ve el tutor y por qué. La arma el
   `ContextRouter` real de `context` (admisión por proyección del rol, candidatos semánticos con
   `via`, hook `Selector`, ledger enter/update/exit); encima, este módulo recorta a `k`, premia
   lo retenido del turno anterior y expande por jerarquía (hermanos vía `child_of`), dejando un
   `reasoning_log` explícito como el del MesaCompiler viejo.
2. La *respuesta* (`build_agent` + `answer`): un `pydantic_ai.Agent` con la persona y la política
   del `AgentDoc` como instrucciones, la mesa inyectada como sección de sistema y dos tools de
   lectura (`show_atom`, `explore`) sobre el `KbReader` de `agents`, scoped a la proyección.

    from tutor.agent import answer, Conversation
    turn = answer("¿Qué es la encapsulación?", model="test")
    turn.reply, turn.mesa["atom_ids"], turn.mesa["reasoning_log"]
    chat = Conversation(kb=kb, model="google-gla:gemini-2.5-flash")
    chat.ask("¿Y la interiorización?")
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models import Model, infer_model
from pydantic_ai.usage import UsageLimits

from agents.kb_tools import KbReader
from agents.run import usage_of
from context import Context, ContextRouter, RoleRoute, RouteContextConfig, Selector
from context.atoms import AtomEntry
from kb import Document, KnowledgeBase
from llm import LlmSettings, LlmUnknownModel, ScriptedModel, ScriptedStep, capabilities_of, make_model
from ontology import Ref
from tutor import world

log = logging.getLogger(__name__)

TEST_MODEL = "test"
SESSION = "tutor-cli"
#: Cupo de la mesa para lo retenido del turno anterior: `k // RETAIN_DIVISOR` átomos (al menos 1),
#: los mejor puntuados hoy entre los de la mesa previa (el `retained_from_previous` del compilador viejo).
RETAIN_DIVISOR = 4
#: Puntaje mínimo de similitud para entrar como candidato semántico.
MIN_RELEVANCE = 0.2
#: Hermanos que se agregan por jerarquía, como máximo, por turno.
EXPAND = 2
#: Cuántos candidatos ve el selector LLM, si lo hay.
SELECTOR_POOL = 30
#: Peticiones al modelo por turno: la primera más las iteraciones con tools.
MAX_REQUESTS = 6
#: Prefijos de Gemini de pydantic-ai 1.x que 2.x conoce como `google:` (GEMINI_API_KEY / GOOGLE_API_KEY).
GOOGLE_ALIASES = frozenset({"google-gla", "google-vertex"})

CITATION_POLICY = (
    "Cita la evidencia con su id entre corchetes, por ejemplo `[atom-action-is-a-core-mental-"
    "structure-in-apos]`, usando solo ids que aparecen en el conocimiento disponible o que leíste "
    "con `show_atom`. Si necesitas algo que no está en la mesa, búscalo con `explore` y léelo con "
    "`show_atom` antes de afirmarlo; nunca inventes un id."
)


@dataclass
class TurnResult:
    """Lo que devuelve un turno: la respuesta y la mesa que la sostiene."""

    reply: str
    mesa: dict[str, Any]
    usage: dict[str, Any] | None
    model: str
    question: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------------------------
# La mesa: ContextRouter real + recorte, retención y expansión por jerarquía
# --------------------------------------------------------------------------------------------


def build_context(
    kb: KnowledgeBase,
    question: str,
    *,
    role: str = "tutor",
    previous: TurnResult | None = None,
    selector: Selector | None = None,
    k: int = 8,
) -> dict[str, Any]:
    """La mesa del turno: `{query, atom_ids, items[{atom_id,title,score,why,role,tags}], reasoning_log, ...}`.

    Corre el `ContextRouter` de `context` sobre un `Context` mínimo (sesión fija, sin paso ni perfil):
    candidatos por `kb.rank` dentro de la proyección del rol, el hook `selector` si viene, y el ledger
    de entradas/salidas. Luego recorta a `k` premiando lo que ya estaba en la mesa anterior y agrega
    hasta `EXPAND` hermanos por `child_of` de los mejores átomos.
    """
    agent_doc = world.agent(kb, role) or {}
    projection = str(agent_doc.get("projection") or role)
    previous_mesa = (previous.mesa if previous else None) or {}
    previous_ids: list[str] = list(previous_mesa.get("atom_ids") or [])
    turn = int(previous_mesa.get("turn") or 0) + 1

    context = _context_from(kb, previous_mesa, turn)
    context.open_turn(question, None)
    route = RoleRoute(
        semantic=True,
        min_relevance=MIN_RELEVANCE,
        select="llm" if selector is not None else "heuristic",
        # el selector ve toda la porción admitida: la KB es chica y así un id válido nunca se descarta
        llm_pool=max(SELECTOR_POOL, len(kb.in_projection(projection))),
    )
    router = ContextRouter(
        RouteContextConfig(roles={role: route}),
        kb,
        projections={role: projection},
        selector=_SelectorAdapter(kb, selector) if selector is not None else None,
    )
    router.route(context)

    entries = context.active.get(role, [])
    events = [e for e in context.ledger if e.turn == turn]
    atoms = {e.key: kb.get(e.key) for e in entries if _is_atom(kb.get(e.key))}

    # Recorte a `k` en tres cupos explícitos: lo retenido de la mesa anterior (lo mejor puntuado
    # hoy, hasta RETAIN_SLOTS), lo nuevo por puntaje, y hermanos por jerarquía (hasta EXPAND).
    ranked = sorted((e for e in entries if e.key in atoms), key=lambda e: (-(e.score or 0.0), e.reason, e.key))
    kept = [e for e in ranked if atoms[e.key].name in previous_ids][: max(1, k // RETAIN_DIVISOR)]
    kept_keys = {e.key for e in kept}
    budget = max(k - len(kept) - EXPAND, 1)
    chosen_fresh = [e for e in ranked if e.key not in kept_keys][:budget]

    selected: list[dict[str, Any]] = []
    for entry in sorted(kept + chosen_fresh, key=lambda e: (-(e.score or 0.0), e.key)):
        document = atoms[entry.key]
        retained = document.name in previous_ids
        why = [f"{entry.reason}:{entry.score:.2f}" if entry.score is not None else entry.reason]
        if retained:
            why.append("retained_from_previous")
        selected.append(
            _item(document, round(entry.score or 0.0, 4), "retained" if retained else entry.reason, "; ".join(why))
        )

    expanded = _expand(kb, selected, {e.key: e for e in entries}, k)
    selected.extend(expanded)
    # Si la jerarquía no llenó su cupo, el resto vuelve a lo nuevo por puntaje.
    taken = {i["atom_id"] for i in selected}
    for entry in (e for e in ranked if atoms[e.key].name not in taken):
        if len(selected) >= k:
            break
        selected.append(_item(atoms[entry.key], round(entry.score or 0.0, 4), entry.reason, f"{entry.reason}:{entry.score or 0.0:.2f}"))
        taken.add(atoms[entry.key].name)
    # Venga por el cupo que venga, lo que ya estaba en la mesa anterior se marca como retenido.
    for item in selected:
        if item["atom_id"] in previous_ids:
            item["role"] = "retained"
            if "retained_from_previous" not in item["why"]:
                item["why"] += "; retained_from_previous"

    selected_ids = [i["atom_id"] for i in selected]
    retained_ids = [i for i in previous_ids if i in selected_ids]
    removed_ids = [i for i in previous_ids if i not in selected_ids]
    added_ids = [i for i in selected_ids if i not in previous_ids]
    reasoning_log = [
        {"type": "query", "detail": question},
        {"type": "role", "detail": role},
        {"type": "projection", "detail": projection},
        {"type": "turn", "detail": turn},
        {"type": "selector", "detail": "llm" if selector is not None else "heuristic"},
        {"type": "admitted", "detail": len(entries)},
        {
            "type": "ledger",
            "detail": [
                {"action": e.action, "ref": e.ref.id, "reason": e.reason} for e in events
            ],
        },
        {"type": "previous_atom_ids", "detail": previous_ids},
        {"type": "retained_atom_ids", "detail": retained_ids},
        {"type": "removed_atom_ids", "detail": removed_ids},
        {"type": "added_atom_ids", "detail": added_ids},
        {"type": "expanded_atom_ids", "detail": [i["atom_id"] for i in expanded]},
        {
            "type": "candidate_scores",
            "detail": [
                {"atom_id": i["atom_id"], "score": i["score"], "role": i["role"], "why": i["why"]}
                for i in selected
            ],
        },
    ]
    summary = [
        f"{len(entries)} admitidos en la proyección {projection}",
        f"se seleccionaron {len(selected)} atoms (k={k}, +{len(expanded)} por jerarquía)",
    ]
    if retained_ids:
        summary.append(f"se retuvieron {len(retained_ids)} atoms previos")
    if removed_ids:
        summary.append(f"se removieron {len(removed_ids)} atoms previos")
    return {
        "query": question,
        "role": role,
        "projection": projection,
        "turn": turn,
        "atom_ids": selected_ids,
        "items": selected,
        "retained_atom_ids": retained_ids,
        "removed_atom_ids": removed_ids,
        "added_atom_ids": added_ids,
        "reasoning_summary": summary,
        "reasoning_log": reasoning_log,
    }


class _SelectorAdapter:
    """Presenta el hook `Selector` tal cual (`select(role, question, step, pool)`) y acepta que
    devuelva ids pelados (`atom-…`) además de claves `Modelo:nombre`, que es lo que el ruteador exige."""

    def __init__(self, kb: KnowledgeBase, inner: Selector) -> None:
        self.inner = inner
        self.keys = {d.name: d.key for d in kb.documents()}

    def select(
        self, role: str, question: str, step: str | None, pool: list[tuple[str, str]]
    ) -> list[str] | None:
        chosen = self.inner.select(role, question, step, pool)
        if chosen is None:
            return None
        return [self.keys.get(ref, ref) for ref in chosen]


def _context_from(kb: KnowledgeBase, previous_mesa: dict[str, Any], turn: int) -> Context:
    """El `Context` del ruteador, reconstruido desde la mesa anterior: sus átomos siguen activos
    (`since_turn` conservado) y el ruteador decide si se quedan o salen."""
    context = Context.new(SESSION)
    context.turn = turn - 1
    role = str(previous_mesa.get("role") or "tutor")
    entries: list[AtomEntry] = []
    for item in previous_mesa.get("items") or []:
        try:
            document = kb.get(str(item["atom_id"]))
        except KeyError:
            continue
        entries.append(
            AtomEntry(
                ref=Ref(kind="kb", id=document.key),
                reason=str(item.get("via") or "semantic"),
                score=item.get("score"),
                since_turn=int(item.get("since_turn") or context.turn or 1),
                last_selected=context.turn,
                content_hash=document.content_hash,
            )
        )
    if entries:
        context.active[role] = entries
    return context


def _expand(
    kb: KnowledgeBase, selected: list[dict[str, Any]], active: dict[str, AtomEntry], k: int
) -> list[dict[str, Any]]:
    """Hermanos (misma rama `child_of`) de los mejores átomos que no estén ya en la mesa."""
    chosen = {i["atom_id"] for i in selected}
    extra: list[dict[str, Any]] = []
    for item in selected[: max(1, k // 3)]:
        branch = world.parent(kb, item["atom_id"])
        if branch is None:
            continue
        for sibling in world.children(kb, branch["id"]):
            if len(extra) >= EXPAND:
                return extra
            if sibling["id"] in chosen or not _is_atom(kb.get(sibling["id"])):
                continue
            entry = active.get(kb.get(sibling["id"]).key)
            score = round(entry.score, 4) if entry and entry.score is not None else 0.0
            chosen.add(sibling["id"])
            extra.append(
                _item(
                    kb.get(sibling["id"]),
                    score,
                    "expanded",
                    f"sibling_of:{item['atom_id']}; parent:{branch['id']}",
                )
            )
    return extra


def _item(document: Document, score: float, role: str, why: str) -> dict[str, Any]:
    return {
        "atom_id": document.name,
        "title": str(document.payload.get("title") or document.name),
        "score": score,
        "why": why,
        "role": role,
        "via": role if role not in {"retained", "expanded"} else "semantic",
        "tags": list(document.tags),
    }


def _is_atom(document: Document) -> bool:
    return world.KNOWLEDGE_MODEL in (document.model, *document.ancestors)


# --------------------------------------------------------------------------------------------
# El agente: instrucciones desde el AgentDoc, mesa como sistema, tools sobre KbReader
# --------------------------------------------------------------------------------------------


class TutorTools:
    """`show_atom` y `explore` para el modelo, sobre el `KbReader` de `agents` (solo la proyección
    del rol; lo leído queda en `reader.reads`). Aceptan ids pelados o `Modelo:nombre`."""

    def __init__(self, kb: KnowledgeBase, projection: str) -> None:
        self.kb = kb
        self.reader = KbReader(kb, projection, ["kb.explore_multi", "kb.show"])
        self.keys = {d.name: d.key for d in self.reader.visible.values()}

    def show_atom(self, atom_id: str) -> str:
        """Lee el contenido completo de un átomo de la KB por su id (`atom-…`). Lo que leas lo puedes citar."""
        key = atom_id.strip().strip("[]`")
        return self.reader.kb_show(self.keys.get(key, key))

    def explore(self, query: str, max_results: int = 5) -> str:
        """Busca en la KB del tutor los átomos más parecidos a `query`; una línea por átomo: id · título · puntaje."""
        hits = self.kb.rank(query, k=max_results, among=list(self.reader.visible))
        lines = [f"{h.name} · {h.document.payload.get('title') or h.name} · {h.score:.2f}" for h in hits]
        return "\n".join(lines) or "sin resultados"

    @property
    def reads(self) -> list[str]:
        return [key.rpartition(":")[2] for key in self.reader.reads]


def instructions_for(kb: KnowledgeBase, role: str = "tutor") -> str:
    """Persona (`framing`) + política (`instructions`) del `AgentDoc` del rol + política de citas."""
    doc = world.agent(kb, role) or {}
    parts = [str(doc.get("framing") or "").strip(), str(doc.get("instructions") or "").strip(), CITATION_POLICY]
    return "\n\n---\n\n".join(p for p in parts if p)


def render_mesa(items: list[dict[str, Any]], kb: KnowledgeBase) -> str:
    """La mesa como sección de sistema: id, título, respuesta y procedencia de cada átomo."""
    blocks: list[str] = []
    for item in items:
        atom = world.get_atom(kb, item["atom_id"]) or {}
        lines = [f"### [{item['atom_id']}] {item['title']}", str(atom.get("summary") or "").strip()]
        if atom.get("question"):
            lines.insert(1, f"Pregunta: {atom['question']}")
        if atom.get("provenance"):
            lines.append(f"Fuente: {str(atom['provenance']).strip()}")
        blocks.append("\n".join(line for line in lines if line))
    body = "\n\n".join(blocks) or "(sin átomos para esta pregunta)"
    return f"## Conocimiento disponible (mesa del turno)\n\n{body}"


def build_agent(
    kb: KnowledgeBase,
    *,
    model: Model | str,
    role: str = "tutor",
    mesa_items: list[dict[str, Any]],
    tools: TutorTools | None = None,
) -> Agent[None, str]:
    """El `Agent` de pydantic-ai del turno: instrucciones del rol + mesa como sistema + tools de KB."""
    projection = str((world.agent(kb, role) or {}).get("projection") or role)
    tools = tools or TutorTools(kb, projection)
    return Agent(
        resolve_model(model) if isinstance(model, str) else model,
        deps_type=type(None),
        output_type=str,
        instructions=[instructions_for(kb, role), render_mesa(mesa_items, kb)],
        tools=[tools.show_atom, tools.explore],
    )


def resolve_model(name: str) -> Model:
    """`provider:model` → un `Model` de pydantic-ai. Pares con capacidades declaradas en `llm`
    (openai, openrouter, bedrock) salen de `llm.make_model`, con sus reintentos; el resto
    (`google-gla:gemini-2.5-flash`, `anthropic:…`) de `pydantic_ai.models.infer_model`."""
    if name == TEST_MODEL:
        return infer_model("test")
    provider, sep, model_name = name.partition(":")
    if provider in GOOGLE_ALIASES:  # pydantic-ai 2.x unificó `google-gla:`/`google-vertex:` en `google:`
        provider, name = "google", f"google:{model_name}"
    if sep:
        settings = LlmSettings(provider=provider, model=model_name)
        try:
            capabilities_of(settings)
        except LlmUnknownModel:
            pass
        else:
            return make_model(settings, verify=False)
    return infer_model(name)


def _test_model(mesa: dict[str, Any]) -> Model:
    """El doble de `llm` para `model="test"`: una respuesta guionada que cita la mesa, sin red."""
    items = mesa.get("items") or []
    if items:
        cited = "\n".join(f"- [{i['atom_id']}] {i['title']}" for i in items[:3])
        text = (
            f"(modelo de prueba) Para «{mesa.get('query', '')}» la mesa trae {len(items)} átomos; "
            f"los más relevantes:\n{cited}"
        )
    else:
        text = "(modelo de prueba) La mesa no trae átomos para esta pregunta."
    return ScriptedModel([ScriptedStep(text=text)]).model


# --------------------------------------------------------------------------------------------
# Un turno y una conversación
# --------------------------------------------------------------------------------------------


def answer(
    question: str,
    *,
    kb: KnowledgeBase | None = None,
    kb_root: Path | None = None,
    model: Model | str = TEST_MODEL,
    role: str = "tutor",
    previous: TurnResult | None = None,
    selector: Selector | None = None,
    message_history: list[ModelMessage] | None = None,
    k: int = 8,
) -> TurnResult:
    """Un turno completo: mesa → agente → respuesta. `model="test"` responde sin red."""
    kb = kb or world.open_kb(kb_root)
    mesa = build_context(kb, question, role=role, previous=previous, selector=selector, k=k)
    projection = str((world.agent(kb, role) or {}).get("projection") or role)
    tools = TutorTools(kb, projection)
    resolved = _test_model(mesa) if model == TEST_MODEL else (resolve_model(model) if isinstance(model, str) else model)
    agent = build_agent(kb, model=resolved, role=role, mesa_items=mesa["items"], tools=tools)
    result = agent.run_sync(
        question, message_history=message_history or [], usage_limits=UsageLimits(request_limit=MAX_REQUESTS)
    )
    if tools.reads:
        mesa["reads"] = tools.reads
        mesa["reasoning_log"].append({"type": "reads", "detail": tools.reads})
    model_label = model if isinstance(model, str) else f"{resolved.system}:{resolved.model_name}"
    return TurnResult(
        reply=str(result.output),
        mesa=mesa,
        usage=usage_of(result).model_dump(),
        model=model_label,
        question=question,
    )


@dataclass
class Conversation:
    """Multi-turno en memoria: los `TurnResult` y el `message_history` compacto de pydantic-ai
    (pregunta/respuesta por turno; la mesa de cada turno va en sus instrucciones, no en el historial)."""

    kb: KnowledgeBase
    model: Model | str = TEST_MODEL
    role: str = "tutor"
    selector: Selector | None = None
    k: int = 8
    turns: list[TurnResult] = field(default_factory=list)
    message_history: list[ModelMessage] = field(default_factory=list)

    def ask(self, question: str) -> TurnResult:
        turn = answer(
            question,
            kb=self.kb,
            model=self.model,
            role=self.role,
            previous=self.turns[-1] if self.turns else None,
            selector=self.selector,
            message_history=list(self.message_history),
            k=self.k,
        )
        self.turns.append(turn)
        self.message_history.extend(
            [ModelRequest(parts=[UserPromptPart(question)]), ModelResponse(parts=[TextPart(turn.reply)])]
        )
        return turn

    @property
    def last(self) -> TurnResult | None:
        return self.turns[-1] if self.turns else None


__all__ = [
    "Conversation",
    "TurnResult",
    "TutorTools",
    "answer",
    "build_agent",
    "build_context",
    "instructions_for",
    "render_mesa",
    "resolve_model",
]
