"""Las capacidades de Pydantic AI con que corre cada agente (05 §6.1, I4; 04 §6.5).

- Políticas como `Hooks`: `deny_if_no_context` corta la corrida antes de llamar al modelo.
- La ventana `history:N` como `ProcessHistory`: el modelo ve los últimos N mensajes previos.
- `Instrumentation`: spans de OpenTelemetry por corrida, petición y tool, sin el texto salvo con
  `log_prompts` (sin proveedor de trazas configurado, no salen del proceso; ver
  `assembly.telemetry`).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import cast

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability, Hooks, Instrumentation, ProcessHistory
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.models.instrumented import InstrumentationSettings

from agents.compile import KNOWLEDGE_FIELDS, CompiledAgent
from agents.declaration import Policy


class PolicyDenied(Exception):
    """Una política decidió no llamar al modelo; el mensaje va a `interventions`."""


def deny_if_no_context(context: Mapping[str, object], reads_kb: bool) -> str | None:
    """Sin conocimiento en el turno ni tools para buscarlo, no se llama al modelo."""
    if reads_kb or any(context.get(field) for field in KNOWLEDGE_FIELDS | {"history"}):
        return None
    return "deny_if_no_context: el turno no trae conocimiento"


#: Cada política: (contexto del turno, ¿lee la KB?) → motivo para no correr, o None.
POLICIES: dict[Policy, Callable[[Mapping[str, object], bool], str | None]] = {
    "deny_if_no_context": deny_if_no_context,
}


def capabilities(
    agent: CompiledAgent,
    context: Mapping[str, object],
    reads_kb: bool,
    prior: int,
    log_prompts: bool = False,
) -> list[AbstractCapability[None]]:
    """Las capacidades de una corrida: políticas, ventana de historial e instrumentación.

    Los spans llevan modelo, tokens, tools y tiempos; el texto de prompts y respuestas solo con
    `log_prompts` (04 D3), aunque ya venga anonimizado.
    """
    settings = InstrumentationSettings(include_content=log_prompts, include_binary_content=log_prompts)
    found: list[AbstractCapability[None]] = [
        policy_hooks(agent.policies, context, reads_kb),
        history_window(agent.history, prior),
        Instrumentation(settings),
    ]
    return found


def policy_hooks(policies: Sequence[str], context: Mapping[str, object], reads_kb: bool) -> Hooks[None]:
    def before_run(ctx: RunContext[None]) -> None:
        for policy in policies:
            reason = POLICIES[cast(Policy, policy)](context, reads_kb)
            if reason is not None:
                raise PolicyDenied(reason)

    return Hooks(before_run=before_run)


def history_window(limit: int | None, prior: int) -> ProcessHistory[None]:
    """De los `prior` mensajes previos quedan los últimos `limit`, empezando por la persona; los de
    la corrida (pregunta, tools, respuestas) no se tocan. Sin `history:N`, ninguno previo."""

    def window(messages: list[ModelMessage]) -> list[ModelMessage]:
        kept = messages[:prior][-limit:] if limit else []
        while kept and not _from_user(kept[0]):
            kept = kept[1:]
        return kept + messages[prior:]

    return ProcessHistory(window)


def _from_user(message: ModelMessage) -> bool:
    return isinstance(message, ModelRequest) and any(isinstance(p, UserPromptPart) for p in message.parts)
