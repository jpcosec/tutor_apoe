from __future__ import annotations

from typing import cast

import pytest
from pydantic import BaseModel
from pydantic_ai.messages import TextPart, UserPromptPart
from pydantic_ai.toolsets import FunctionToolset

from agents import (
    AgentDecl,
    AgentRunner,
    CompiledAgent,
    HistoryMessage,
    InstructionVariant,
    Profile,
    compile_agent,
    holds,
    instructions_for,
    render_context,
)
from kb import KnowledgeBase
from llm import ScriptedModel, ScriptedStep


def compiled(**overrides: object) -> CompiledAgent:
    base: dict[str, object] = {
        "role": "conversador",
        "instructions": "BASE",
        "instruction_variants": [
            InstructionVariant(
                ref="StyleGuide:grande", applies_when=["profile.tipo_empresa == grande"], text="USTED"
            ),
            InstructionVariant(
                ref="StyleGuide:persona", applies_when=["profile.tipo_empresa == persona"], text="TU"
            ),
        ],
        "dynamic_fields": ["bundle", "question"],
        "history": 2,
        "on_failure": "closed",
        "projection": "all",
        "max_tool_iterations": 4,
        "source_sha256": "x",
    }
    return CompiledAgent.model_validate({**base, **overrides})


@pytest.mark.parametrize(
    ("condition", "ficha", "traits", "expected"),
    [
        ("profile.tipo_empresa == grande", {"tipo_empresa": "grande"}, [], True),
        ("profile.tipo_empresa != grande", {"tipo_empresa": "grande"}, [], False),
        ("profile.tramo in [a, b]", {"tramo": "b"}, [], True),
        ("trait:evita", {}, ["evita"], True),
        ("trait:evita", {}, [], False),
        ("fuera de gramatica", {}, [], False),
    ],
)
def test_condiciones(condition: str, ficha: dict[str, object], traits: list[str], expected: bool) -> None:
    assert holds(condition, Profile(ficha=ficha, traits=traits)) is expected


def test_variante_por_segmento() -> None:
    agent = compiled()

    grande = instructions_for(agent, Profile(ficha={"tipo_empresa": "grande"}))
    pyme = instructions_for(agent, Profile(ficha={"tipo_empresa": "pyme"}))

    assert (grande.text, grande.variant) == ("BASE\n\nUSTED", "StyleGuide:grande")
    assert (pyme.text, pyme.variant) == ("BASE", None)


def test_contexto_dinamico_con_pregunta_al_final() -> None:
    text = render_context(compiled(), {"question": "hola", "bundle": ["[A:b]\ntexto"]})

    assert text.index("Conocimiento relevante") < text.index("Mensaje de la persona")
    with pytest.raises(KeyError, match="bundle"):
        render_context(compiled(), {"question": "hola"})


def test_runner_con_historial_y_fallo() -> None:
    ok = ScriptedModel([ScriptedStep(text="respuesta")])
    history = [
        HistoryMessage(role="user", text="a"),
        HistoryMessage(role="assistant", text="b"),
        HistoryMessage(role="user", text="c"),
        HistoryMessage(role="assistant", text="d"),
    ]

    output = AgentRunner(compiled(), ok.model).run({"question": "q", "bundle": []}, Profile(), history)
    failed = AgentRunner(compiled(), ScriptedModel([]).model).run(
        {"question": "q", "bundle": []}, Profile(), []
    )

    assert output.text == "respuesta"
    assert len(ok.received[0]) == 3  # dos del historial (history:2) y el turno
    assert (failed.failed, failed.text) == (True, "No puedo procesar ahora.")


def test_un_esquema_desconocido_no_compila() -> None:
    decl = AgentDecl(role="x", on_failure="open", output_schema="Inventado@9")

    with pytest.raises(ValueError, match="esquema desconocido"):
        compile_agent(decl, cast(KnowledgeBase, None))


def test_un_kind_de_decision_desconocido_cae_a_fallback_y_no_revienta() -> None:
    """F-04 (contrato genérico): una salida handout inválida termina en respaldo."""
    handout = ScriptedStep(text="", structured={"kind": "handout", "reason": "folleto"})
    model = ScriptedModel([handout, handout])
    output = AgentRunner(compiled(output_schema="TurnDecision@1"), model.model).decide(
        {"question": "q", "bundle": []}, Profile(), []
    )

    assert (output.failed, output.decision.kind) == (True, "fallback")
    assert output.outcome is not None
    assert output.outcome.error_class == "LlmOutputInvalid"


def test_deny_if_no_context_no_llama_al_modelo_sin_conocimiento() -> None:
    model = ScriptedModel([])
    runner = AgentRunner(compiled(policies=["deny_if_no_context"]), model.model)

    output = runner.run({"question": "q", "bundle": []}, Profile(), [])

    assert (output.failed, model.received) == (True, [])
    assert output.interventions == ["deny_if_no_context: el turno no trae conocimiento"]


class _Folio(BaseModel):
    folio: str


def _folio_toolset(calls: list[str]) -> FunctionToolset[None]:
    def detalle_factura(args: _Folio) -> dict[str, object]:
        """Las facturas de la persona."""
        calls.append(args.folio)
        return {"status": "ok", "monto": "$80.000"}

    return FunctionToolset([detalle_factura])


def _call(arguments: dict[str, object]) -> ScriptedStep:
    return ScriptedStep(text="", tool_calls=[{"name": "detalle_factura", "arguments": arguments}])


def test_el_decisor_llama_la_tool_y_pydantic_ai_corrige_argumentos_invalidos() -> None:
    """La validación de argumentos y el reintento los hace Pydantic AI (docs/reemplazos §1.1)."""
    calls: list[str] = []
    steps = [
        _call({}),
        _call({"folio": "1042"}),
        ScriptedStep(text="", structured={"kind": "nl", "reason": "x"}),
    ]
    agent = compiled(output_schema="TurnDecision@1")

    output = AgentRunner(agent, ScriptedModel(steps).model).decide(
        {"question": "q", "bundle": []}, Profile(), [], toolset=_folio_toolset(calls)
    )

    assert (output.failed, output.decision.kind, calls) == (False, "nl", ["1042"])
    assert [(c.name, c.arguments) for c in output.tool_calls] == [
        ("detalle_factura", {}),
        ("detalle_factura", {"folio": "1042"}),
    ]


def test_el_bucle_con_tools_tiene_tope() -> None:
    """`max_tool_iterations` acota las peticiones al modelo (05 I6): una tool inexistente fuerza otra."""
    steps = [
        ScriptedStep(text="", tool_calls=[{"name": "inventada", "arguments": {}}]),
        ScriptedStep(text="ok"),
    ]

    capped = AgentRunner(compiled(max_tool_iterations=0), ScriptedModel(steps).model)
    roomy = AgentRunner(compiled(max_tool_iterations=2), ScriptedModel(list(steps)).model)

    assert capped.run({"question": "q", "bundle": []}, Profile(), []).failed
    assert roomy.run({"question": "q", "bundle": []}, Profile(), []).text == "ok"


def test_la_ventana_de_historial_empieza_por_la_persona_y_la_corrida_informa_su_uso() -> None:
    model = ScriptedModel([ScriptedStep(text="respuesta")])
    history = [
        HistoryMessage(role="user", text="a"),
        HistoryMessage(role="assistant", text="b"),
        HistoryMessage(role="user", text="c"),
        HistoryMessage(role="assistant", text="d"),
        HistoryMessage(role="user", text="sin respuesta"),
    ]
    runner = AgentRunner(compiled(history=3), model.model)

    output = runner.run({"question": "q", "bundle": []}, Profile(), history)

    # sin el mensaje final sin respuesta, history:3 deja "b", "c", "d"; "b" no es de la persona y sale
    texts = [
        part.content
        for message in model.received[0]
        for part in message.parts
        if isinstance(part, UserPromptPart | TextPart) and isinstance(part.content, str)
    ]
    assert texts[:2] == ["c", "d"]
    assert texts[2].endswith("q")
    assert output.usage.requests == 1
    assert output.usage.input_tokens > 0
    assert output.usage.cost_usd is None  # el modelo guionado no tiene precio


def test_la_seccion_citada_nombra_cada_documento_para_que_el_agente_lo_pueda_referir() -> None:
    from types import SimpleNamespace
    from typing import Any

    from agents import StaticSection
    from agents.providers import section

    class Criteria:
        documents = [
            SimpleNamespace(
                key="GateCriterion:gate-a",
                name="gate-a",
                model_tags=["type.gate"],
                payload={"title": "Sin A"},
            )
        ]

        def eligible(self) -> list[Any]:
            return self.documents

        def render(self, ref: str) -> str:
            return "# Sin A\n\n## Criterion\n\nNo dice A."

    spec = StaticSection(tag="type.gate", title="Criterios", render="cited")

    text = section(cast(KnowledgeBase, Criteria()), spec, "gate")

    assert text == "## Criterios\n\n### Sin A [GateCriterion:gate-a]\n\n### Criterion\n\nNo dice A."
