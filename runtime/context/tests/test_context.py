"""Contexto (14): ruteo por rol con ledger, proyección determinista, bindings y persistencia."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from agents import CompiledAgent, HistoryMessage, Profile
from context import (
    Context,
    ContextRouter,
    InMemoryContextStore,
    LlmSelector,
    RoleRoute,
    RouteContextConfig,
    TurnSummary,
    load,
    project,
    replay_active,
    save,
)
from data import Privacy, Scrubber, SqlStore, Vault
from kb import KnowledgeBase
from llm import ScriptedModel, ScriptedStep
from semantics import Ontology

STEP_A, STEP_B = "ConversationStep:step-a", "ConversationStep:step-b"


@dataclass
class Doc:
    key: str
    tags: list[str] = field(default_factory=list[str])
    payload: dict[str, object] = field(default_factory=dict[str, object])
    model_tags: list[str] = field(default_factory=lambda: ["type.knowledge.domain"])
    content_hash: str = "h-1"


@dataclass
class FakeKb:
    """Lo que el ruteador y la proyección usan de 01: porciones, aristas, tags, ranking y render."""

    docs: dict[str, Doc] = field(default_factory=dict[str, Doc])
    views: dict[str, list[str]] = field(default_factory=dict[str, list[str]])  # proyección → claves
    reads: dict[str, list[str]] = field(default_factory=dict[str, list[str]])  # proyección → relaciones
    edges: dict[tuple[str, str], list[str]] = field(default_factory=dict[tuple[str, str], list[str]])
    hits: list[tuple[str, float]] = field(default_factory=list[tuple[str, float]])
    fingerprint: str = "kb-1"

    def add(self, key: str, **fields: Any) -> FakeKb:
        self.docs[key] = Doc(key=key, **fields)
        return self

    def in_projection(self, name: str = "all") -> list[Doc]:
        keys = self.views.get(name, list(self.docs))
        return [self.docs[k] for k in keys if k in self.docs]

    def projection(self, name: str = "all") -> SimpleNamespace:
        return SimpleNamespace(relations=self.reads.get(name, ["grounded_by", "transitions_to"]))

    def outgoing(self, ref: str, relation_type: str | None = None) -> list[SimpleNamespace]:
        return [SimpleNamespace(target_ref=t) for t in self.edges.get((ref, relation_type or ""), [])]

    def tag_scope(self, tag: str) -> frozenset[str]:
        tags = {t for d in self.docs.values() for t in d.tags}
        return frozenset({tag, *(t for t in tags if t.startswith(f"{tag}."))})

    def rank(
        self, query: str, k: int = 10, *, threshold: float = 0.0, among: list[str] | None = None
    ) -> list[Any]:
        allowed = set(among or [])
        found = [SimpleNamespace(ref=r, score=s) for r, s in self.hits if s >= threshold and r in allowed]
        return found[:k]

    def eligible(self) -> list[Doc]:
        return []

    def get(self, ref: str) -> Doc:
        return self.docs.get(ref) or Doc(key=ref)

    def render(self, ref: str) -> str:
        return f"# {ref}\n\nContenido de {ref}."


def router(
    kb: FakeKb, roles: tuple[str, ...] = ("redactor",), tools: list[str] | None = None
) -> ContextRouter:
    config = RouteContextConfig(roles={role: RoleRoute() for role in roles})
    return ContextRouter(config, cast(KnowledgeBase, kb), {role: role for role in roles}, tools)


def next_turn(context: Context, step: str | None, question: str = "hola") -> Context:
    """Lo que hace `compile_context` y `save_context` alrededor del ruteo, sin el resto del turno."""
    if context.turn:
        context.trace.append(
            TurnSummary(
                turn=context.turn,
                question=context.question,
                step_before=context.current_step,
                step_after=step,
            )
        )
    context.turn += 1
    context.current_step, context.question = step, question
    return context


def keys(context: Context, role: str = "redactor") -> list[str]:
    return [e.key for e in context.active.get(role, [])]


def reasons(context: Context, role: str = "redactor") -> dict[str, str]:
    return {e.key: e.reason for e in context.active.get(role, [])}


def kb_con_cada_fuente() -> FakeKb:
    """Un paso con arista, un átomo marcado con el tag del paso, uno por segmento y uno parecido."""
    kb = FakeKb(edges={(STEP_A, "grounded_by"): ["DomainAtom:pago"]}, hits=[("RuleAtom:tono", 0.9)])
    kb.add(STEP_A, tags=["conversation:steps.a"], model_tags=["type.knowledge.step"])
    kb.add("DomainAtom:pago").add("RuleAtom:tono")
    kb.add("DomainAtom:del-paso", tags=["conversation:steps.a.detalle"])
    kb.add("DomainAtom:empresas", payload={"applies_when": ["profile.tipo == grande"]})
    return kb


def test_cada_fuente_de_la_kb_entra_con_su_motivo_y_en_orden() -> None:
    context = next_turn(Context.new("s-1"), STEP_A)
    context.profile = Profile(ficha={"tipo": "grande"})

    context = router(kb_con_cada_fuente()).route(context)

    assert reasons(context) == {
        "DomainAtom:pago": "step:grounded_by",
        "DomainAtom:del-paso": "step:tag",
        "DomainAtom:empresas": "profile",
        "RuleAtom:tono": "semantic",
    }
    assert keys(context)[-1] == "RuleAtom:tono"


def test_cada_rol_consulta_solo_su_porcion_de_la_kb() -> None:
    kb = kb_con_cada_fuente()
    kb.views = {"decisor": [STEP_A], "redactor": ["DomainAtom:pago", "RuleAtom:tono"]}

    context = router(kb, roles=("decisor", "redactor")).route(next_turn(Context.new("s-1"), STEP_A))

    assert keys(context, "decisor") == []
    assert keys(context, "redactor") == ["DomainAtom:pago", "RuleAtom:tono"]


def test_lo_de_otro_segmento_y_las_tools_no_habilitadas_no_entran() -> None:
    kb = kb_con_cada_fuente().add(
        "ReadToolAtom:tool-x", payload={"name": "otra_tool"}, model_tags=["type.knowledge.tool"]
    )
    kb.hits.append(("ReadToolAtom:tool-x", 0.95))
    context = next_turn(Context.new("s-1"), STEP_A)
    context.profile = Profile(ficha={"tipo": "persona"})

    context = router(kb, tools=["detalle"]).route(context)

    assert "DomainAtom:empresas" not in keys(context)
    assert "ReadToolAtom:tool-x" not in keys(context)


@pytest.mark.spec("14-C2")
def test_al_cambiar_de_paso_sale_lo_del_paso_y_lo_parecido_se_queda() -> None:
    kb = kb_con_cada_fuente()
    route = router(kb)
    context = route.route(next_turn(Context.new("s-1"), STEP_A))
    kb.hits = []

    context = route.route(next_turn(context, STEP_B))

    assert keys(context) == ["RuleAtom:tono"]
    assert {e.ref.id: e.reason for e in context.ledger if e.action == "exit"} == {
        "DomainAtom:pago": "step_change",
        "DomainAtom:del-paso": "step_change",
    }
    assert replay_active(context.ledger) == {"redactor": [e.ref for e in context.active["redactor"]]}


def test_lo_que_ya_no_se_elige_no_sale_por_tiempo() -> None:
    kb = kb_con_cada_fuente()
    route = router(kb)
    context = route.route(next_turn(Context.new("s-1"), None))
    kb.hits = []

    for _ in range(5):
        context = route.route(next_turn(context, None))

    assert keys(context) == ["RuleAtom:tono"]
    entry = context.active["redactor"][0]
    assert (entry.since_turn, entry.last_selected) == (1, 1)


def test_si_el_perfil_cambia_sale_lo_que_ya_no_aplica() -> None:
    route = router(kb_con_cada_fuente())
    context = next_turn(Context.new("s-1"), None)
    context.profile = Profile(ficha={"tipo": "grande"})
    context = route.route(context)

    context = next_turn(context, None)
    context.profile = Profile(ficha={"tipo": "persona"})
    context = route.route(context)

    assert "DomainAtom:empresas" not in keys(context)
    assert context.ledger[-1].reason == "inadmissible"


def agent(*fields: str) -> CompiledAgent:
    return CompiledAgent(
        role="redactor",
        instructions="x",
        instruction_variants=[],
        dynamic_fields=list(fields),
        history=None,
        on_failure="closed",
        projection="all",
        max_tool_iterations=1,
        source_sha256="0",
    )


@pytest.mark.spec("14-C3")
def test_la_proyeccion_es_determinista_y_cambia_con_los_atomos() -> None:
    kb = kb_con_cada_fuente()
    kb.edges[(STEP_A, "transitions_to")] = [STEP_B]
    kb.views = {"redactor": ["DomainAtom:pago"]}
    context = router(kb).route(next_turn(Context.new("s-1"), STEP_A, "ya pagué"))
    drafter = agent("bundle", "allowed_transitions", "question")

    first = project(context, drafter, Ontology(cast(KnowledgeBase, kb)))
    second = project(context, drafter, Ontology(cast(KnowledgeBase, kb)))
    context.active["redactor"] = []
    third = project(context, drafter, Ontology(cast(KnowledgeBase, kb)))

    assert first.sha256 == second.sha256 != third.sha256
    assert "Contenido de DomainAtom:pago." in first.text
    assert first.fields["allowed_transitions"] == [STEP_B]


def test_extras_ganan_y_un_campo_sin_fuente_falla() -> None:
    context = next_turn(Context.new("s-1"), None)

    projection = project(
        context, agent("tool_result"), Ontology(cast(KnowledgeBase, FakeKb())), {"tool_result": {"a": 1}}
    )

    assert (
        projection.fields["tool_result"] == "#### Otros datos\n\n| campo | valor |\n| --- | --- |\n| a | 1 |"
    )
    with pytest.raises(KeyError, match="no sale del contexto"):
        project(context, agent("inventado"), Ontology(cast(KnowledgeBase, FakeKb())))


def test_bindings_del_contexto() -> None:
    context = next_turn(Context.new("s-1"), STEP_A)
    context.state["ultimo_envio"] = "SM-1"

    assert context.bindings() == {
        "context.subject": "s-1",
        "context.session": "s-1",
        "context.step": STEP_A,
        "state.ultimo_envio": "SM-1",
    }


@pytest.mark.parametrize("store", [InMemoryContextStore(), SqlStore("sqlite://")], ids=["memoria", "sql"])
def test_guardar_y_cargar_devuelve_el_mismo_contexto(store: Any) -> None:
    context = router(kb_con_cada_fuente()).route(next_turn(Context.new("s-1"), STEP_A))
    context.append_transcript("redactor", [{"kind": "request", "parts": []}])

    save(store, context)

    assert load(store, "s-1") == context
    assert load(store, "otra").turn == 0


@pytest.mark.spec("14-C4")
def test_los_criterios_del_gate_no_se_rutean() -> None:
    kb = FakeKb(edges={(STEP_A, "grounded_by"): ["GateCriterion:datos"]}, hits=[("GateCriterion:datos", 0.9)])
    kb.add("GateCriterion:datos", model_tags=["type.knowledge.gate"])

    context = router(kb).route(next_turn(Context.new("s-1"), STEP_A))

    assert keys(context) == []
    assert context.ledger == []


@pytest.mark.spec("14-C5")
def test_transcripciones_y_trace_se_guardan_anonimizados(tmp_path: Path) -> None:
    vault = Vault(f"sqlite:///{tmp_path / 'vault.sqlite'}")
    store = SqlStore("sqlite://", Privacy(Scrubber(), vault))
    context = next_turn(Context.new("s-1"), None, "mi correo es ana@example.com")
    context.append_transcript("redactor", [{"texto": "escríbele a ana@example.com"}])

    save(store, context)

    loaded = load(store, "s-1")
    assert loaded.question == "mi correo es <EMAIL_1>"
    assert loaded.transcripts["redactor"] == [{"texto": "escríbele a <EMAIL_1>"}]
    assert loaded.ref == context.ref


@pytest.mark.spec("14-C9")
def test_el_modulo_no_conoce_nombres_de_negocio() -> None:
    source = Path(__file__).resolve().parents[1] / "src" / "context"
    text = "\n".join(p.read_text(encoding="utf-8").lower() for p in source.glob("*.py"))

    assert not [word for word in ("demo", "factura", "orchestrator", "conversador", "twilio") if word in text]


@pytest.mark.spec("14-C10")
def test_la_huella_de_la_kb_y_de_cada_atomo_quedan_en_el_contexto() -> None:
    kb = FakeKb(hits=[("RuleAtom:tono", 0.9)]).add("RuleAtom:tono")
    route = router(kb)
    context = route.route(next_turn(Context.new("s-1"), None))
    kb.docs["RuleAtom:tono"].content_hash = "h-2"

    context = route.route(next_turn(context, None))

    assert context.active["redactor"][0].content_hash == "h-2"
    assert [(e.action, e.reason, e.content_hash) for e in context.ledger] == [
        ("enter", "semantic", "h-1"),
        ("update", "content_changed", "h-2"),
    ]
    assert replay_active(context.ledger) == {"redactor": [context.active["redactor"][0].ref]}


@pytest.mark.spec("14-C10")
def test_un_atomo_retenido_cuyo_contenido_cambia_registra_update() -> None:
    """Lo traído por similitud se queda aunque ya no salga; si su contenido cambió, se registra."""
    kb = FakeKb(hits=[("RuleAtom:tono", 0.9)]).add("RuleAtom:tono")
    route = router(kb)
    context = route.route(next_turn(Context.new("s-1"), None))
    kb.hits = []  # ya no sale por ninguna fuente: se retiene
    kb.docs["RuleAtom:tono"].content_hash = "h-2"

    context = route.route(next_turn(context, None))

    assert context.active["redactor"][0].content_hash == "h-2"
    assert [(e.action, e.reason, e.content_hash) for e in context.ledger][-1] == (
        "update",
        "content_changed",
        "h-2",
    )


def test_state_no_se_anonimiza_y_los_bindings_sobreviven_a_la_recarga(tmp_path: Path) -> None:
    store = SqlStore("sqlite://", Privacy(Scrubber(), Vault(f"sqlite:///{tmp_path / 'vault.sqlite'}")))
    context = next_turn(Context.new("s-1"), None)
    context.state["ultimo_envio"] = "56912345678"  # parece teléfono: el anonimizador lo marcaría

    save(store, context)

    assert load(store, "s-1").bindings()["state.ultimo_envio"] == "56912345678"


def test_cada_foto_guarda_solo_las_transcripciones_de_su_turno_y_no_el_historial() -> None:
    store = InMemoryContextStore()
    context = next_turn(Context.new("s-1"), None)
    context.history = [HistoryMessage(role="user", text="hola")]
    context.append_transcript("redactor", [{"turno": 1}])
    save(store, context)

    context = load(store, "s-1")
    context.open_turn("otra", None)
    context.append_transcript("redactor", [{"turno": 2}])
    save(store, context)

    saved = store.load_context("s-1")
    assert saved is not None
    assert "history" not in saved
    assert saved["transcripts"] == {"redactor": [{"turno": 2}]}


@dataclass
class FakeSelector:
    """Devuelve lo que se le diga y guarda lo que vio."""

    choice: list[str] | None
    pools: list[list[str]] = field(default_factory=list[list[str]])

    def select(
        self, role: str, question: str, step: str | None, pool: list[tuple[str, str]]
    ) -> list[str] | None:
        self.pools.append([ref for ref, _ in pool])
        return self.choice


def llm_router(kb: FakeKb, selector: FakeSelector) -> ContextRouter:
    config = RouteContextConfig(roles={"redactor": RoleRoute(select="llm")})
    return ContextRouter(config, cast(KnowledgeBase, kb), {"redactor": "redactor"}, None, None, selector)


def test_con_llm_elige_entre_lo_admitido_y_lo_del_paso_entra_igual() -> None:
    kb = kb_con_cada_fuente().add("GateCriterion:x", model_tags=["type.knowledge.gate"])
    selector = FakeSelector(["RuleAtom:tono", "GateCriterion:x", "DomainAtom:inventado"])
    context = next_turn(Context.new("s-1"), STEP_A)

    context = llm_router(kb, selector).route(context)

    assert reasons(context) == {"DomainAtom:pago": "step:grounded_by", "RuleAtom:tono": "llm"}
    [pool] = selector.pools
    assert "DomainAtom:pago" not in pool  # lo anclado al paso no se consulta
    assert "GateCriterion:x" not in pool  # las guardas de admisión corren antes (14 D7)
    assert pool[:2] == ["DomainAtom:del-paso", "RuleAtom:tono"]  # lo heurístico primero


def test_si_el_modelo_falla_quedan_las_heuristicas() -> None:
    context = next_turn(Context.new("s-1"), STEP_A)

    context = llm_router(kb_con_cada_fuente(), FakeSelector(None)).route(context)

    assert reasons(context) == {
        "DomainAtom:pago": "step:grounded_by",
        "DomainAtom:del-paso": "step:tag",
        "RuleAtom:tono": "semantic",
    }


def test_el_selector_con_llm_devuelve_las_refs_del_modelo() -> None:
    scripted = ScriptedModel(
        [ScriptedStep(text="", structured={"refs": ["RuleAtom:tono"], "reason": "tono"})]
    )

    chosen = LlmSelector(scripted.model).select(
        "redactor", "hola", STEP_A, [("RuleAtom:tono", "Cómo hablar")]
    )

    assert chosen == ["RuleAtom:tono"]
    assert LlmSelector(ScriptedModel([]).model).select("redactor", "hola", None, [("A:b", "b")]) is None
