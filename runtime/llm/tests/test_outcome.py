"""04 §6.4, I3, I4 y P6: el resultado de cada corrida y los cuerpos de saturación."""

from __future__ import annotations

import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart

from llm import FinishReason, LlmRateLimited, ScriptedModel, ScriptedStep, classify, outcome_of
from llm.outcome import finish_reason


def response(*parts: TextPart | ToolCallPart, reason: str | None = None) -> list[ModelMessage]:
    return [ModelResponse(parts=list(parts), finish_reason=reason)]  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("messages", "expected"),
    [
        (response(TextPart("hola"), reason="stop"), FinishReason.stop),
        (response(TextPart("   "), reason="stop"), FinishReason.error),  # I4: vacío nunca es stop
        (response(TextPart("a medias"), reason="length"), FinishReason.max_tokens),
        (response(TextPart(""), reason="content_filter"), FinishReason.content_filtered),
        (response(ToolCallPart("buscar", {"q": "x"})), FinishReason.tool_calls),
        (response(ToolCallPart("final_result", {"text": "x"})), FinishReason.stop),  # salida tipada
        ([], FinishReason.error),
    ],
)
def test_motivo_de_termino(messages: list[ModelMessage], expected: FinishReason) -> None:
    assert finish_reason(messages) == expected


def test_una_corrida_deja_uso_motivo_y_proveedor() -> None:
    model = ScriptedModel([ScriptedStep(text="respuesta")]).model
    result = Agent(model).run_sync("hola")

    outcome = outcome_of(result, latency_ms=12, provider="test", model="guion")

    assert (outcome.finish_reason, outcome.usage.requests, outcome.latency_ms) == (FinishReason.stop, 1, 12)
    assert outcome.attempts.validation == 0
    assert outcome.substrate_version


def test_un_cuerpo_de_saturacion_es_rate_limited_aunque_no_haya_429() -> None:
    assert isinstance(classify(UnexpectedModelBehavior("Provider is overloaded")), LlmRateLimited)
    assert isinstance(classify(RuntimeError("ThrottlingException: slow down"), "bedrock"), LlmRateLimited)
    assert not isinstance(classify(RuntimeError("ThrottlingException"), None), LlmRateLimited)
