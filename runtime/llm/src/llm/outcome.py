"""El resultado de cada corrida del sustrato (04 §6.4, I3, I4).

`finish_reason` sale del último `ModelResponse`: llamada a herramienta → `tool_calls`; término
del proveedor `length` → `max_tokens`; `content_filter` → `content_filtered`; texto no vacío con
término normal → `stop`; texto vacío con término normal → `error`, nunca `stop` (I4).
`attempts.validation` son los reintentos de salida que pidió el sustrato (I6); los transitorios
los cuenta el transporte y aquí no se ven.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
)

from llm.conformance import substrate_version


class FinishReason(StrEnum):
    stop = "stop"
    tool_calls = "tool_calls"
    max_tokens = "max_tokens"
    content_filtered = "content_filtered"
    error = "error"


class Attempts(BaseModel, frozen=True):
    transient: int = 0
    validation: int = 0


class Usage(BaseModel, frozen=True):
    input_tokens: int | None
    output_tokens: int | None
    requests: int
    reported: bool


class RunOutcome(BaseModel, frozen=True):
    finish_reason: FinishReason
    usage: Usage
    attempts: Attempts
    latency_ms: int
    provider: str
    model: str
    substrate_version: str
    error_class: str | None = None


def finish_reason(messages: list[ModelMessage]) -> FinishReason:
    last = next((m for m in reversed(messages) if isinstance(m, ModelResponse)), None)
    if last is None:
        return FinishReason.error
    if any(isinstance(p, ToolCallPart) for p in last.parts) and not _is_final_output(last):
        return FinishReason.tool_calls
    if last.finish_reason == "length":
        return FinishReason.max_tokens
    if last.finish_reason == "content_filter":
        return FinishReason.content_filtered
    text = "".join(p.content for p in last.parts if isinstance(p, TextPart)).strip()
    return FinishReason.stop if text or _is_final_output(last) else FinishReason.error


def outcome_of(result: Any, latency_ms: int, provider: str, model: str) -> RunOutcome:
    """De un `AgentRunResult` de Pydantic AI."""
    messages: list[ModelMessage] = list(result.all_messages())
    usage = result.usage
    reported = bool(usage.input_tokens or usage.output_tokens)
    retries = sum(
        isinstance(part, RetryPromptPart)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
    )
    return RunOutcome(
        finish_reason=finish_reason(messages),
        usage=Usage(
            input_tokens=usage.input_tokens if reported else None,
            output_tokens=usage.output_tokens if reported else None,
            requests=usage.requests,
            reported=reported,
        ),
        attempts=Attempts(validation=retries),
        latency_ms=latency_ms,
        provider=provider,
        model=model,
        substrate_version=substrate_version(),
    )


def failed_outcome(error_class: str, latency_ms: int, provider: str, model: str) -> RunOutcome:
    """Una corrida que no terminó: `finish_reason = error` con la clase del `LlmError`."""
    return RunOutcome(
        finish_reason=FinishReason.error,
        usage=Usage(input_tokens=None, output_tokens=None, requests=0, reported=False),
        attempts=Attempts(),
        latency_ms=latency_ms,
        provider=provider,
        model=model,
        substrate_version=substrate_version(),
        error_class=error_class,
    )


def _is_final_output(response: ModelResponse) -> bool:
    """La salida tipada llega como llamada a la herramienta de salida (`final_result`)."""
    return any(isinstance(p, ToolCallPart) and p.tool_name.startswith("final_result") for p in response.parts)
