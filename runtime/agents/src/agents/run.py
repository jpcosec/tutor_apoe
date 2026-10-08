"""Ejecutar un agente compilado sobre Pydantic AI (05 §6.1): capacidades, salida tipada y fallo."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel, Field
from pydantic_ai import Agent, AgentRunResult, ModelRetry, RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.usage import UsageLimits

from agents.capabilities import PolicyDenied, capabilities
from agents.compile import CompiledAgent
from agents.kb_tools import KbReader
from agents.prompt import instructions_for, render_context
from agents.schemas import (
    SCHEMAS,
    WITH_CLAIMS,
    Claim,
    DraftWithEvidence,
    GateVerdict,
    Respond,
    ToolCallRequest,
    TurnDecision,
)
from agents.segments import Profile
from llm import InternalFault, LlmError, RunOutcome, classify, failed_outcome, outcome_of

#: Último recurso de `on_failure: closed` (05 §4); el despliegue pasa su texto de fallback (06 I7).
FAILURE_TEXT = "No puedo procesar ahora."
OutputT = TypeVar("OutputT")
log = logging.getLogger(__name__)


class HistoryMessage(BaseModel, frozen=True):
    role: str = Field(description="user | assistant")
    text: str = Field(description="Texto ya anonimizado.")


class RunUsageView(BaseModel, frozen=True):
    """Lo que costó una corrida: la traza lo guarda por agente (04 §6.5)."""

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = Field(default=None, description="Con precios de genai-prices; None si no hay.")


class AgentOutput(BaseModel, frozen=True):
    text: str = Field(description="Salida del agente (texto para un drafter).")
    variant: str | None = Field(description="Variante de instrucciones usada.")
    failed: bool = Field(description="True si el modelo falló y se aplicó on_failure.")
    error_class: str | None = Field(default=None, description="Clase del LlmError, si falló.")
    messages: list[dict[str, object]] = Field(
        default_factory=list[dict[str, object]], description="Mensajes nuevos de la corrida (14 §6.5)."
    )
    claims: list[Claim] | None = Field(
        default=None, description="Con DraftWithEvidence@1, las afirmaciones citadas; None sin evidencia."
    )
    reads: list[str] = Field(default_factory=list[str], description="Documentos que leyó con kb_show.")
    step_target: str | None = Field(default=None, description="Con Respond@1, el paso que eligió.")
    interventions: list[str] = Field(default_factory=list[str], description="Políticas que actuaron (05 I4).")
    usage: RunUsageView = Field(default_factory=RunUsageView, description="Peticiones, tokens y costo.")
    outcome: RunOutcome | None = Field(default=None, description="Resultado de la corrida (04 §6.4).")


class DecisionOutput(BaseModel, frozen=True):
    decision: TurnDecision = Field(description="La decisión, o el `fallback` del esquema si falló.")
    failed: bool = Field(description="True si el modelo falló.")
    messages: list[dict[str, object]] = Field(
        default_factory=list[dict[str, object]], description="Mensajes nuevos de la corrida (14 §6.5)."
    )
    reads: list[str] = Field(default_factory=list[str], description="Documentos que leyó con kb_show.")
    interventions: list[str] = Field(default_factory=list[str], description="Políticas que actuaron (05 I4).")
    tool_calls: list[ToolCallRequest] = Field(
        default_factory=list[ToolCallRequest], description="Tools de negocio que llamó en la corrida."
    )
    usage: RunUsageView = Field(default_factory=RunUsageView, description="Peticiones, tokens y costo.")
    outcome: RunOutcome | None = Field(default=None, description="Resultado de la corrida (04 §6.4).")


class ReviewOutput(BaseModel, frozen=True):
    verdict: GateVerdict = Field(description="El veredicto, o el `fallback` del esquema (rechaza) si falló.")
    failed: bool = Field(description="True si el modelo falló o una política cortó la corrida.")
    messages: list[dict[str, object]] = Field(
        default_factory=list[dict[str, object]], description="Mensajes nuevos de la corrida (14 §6.5)."
    )
    interventions: list[str] = Field(default_factory=list[str], description="Políticas que actuaron (05 I4).")
    usage: RunUsageView = Field(default_factory=RunUsageView, description="Peticiones, tokens y costo.")
    outcome: RunOutcome | None = Field(default=None, description="Resultado de la corrida (04 §6.4).")


class AgentRunner:
    def __init__(
        self,
        agent: CompiledAgent,
        model: Model,
        settings: ModelSettings | None = None,
        log_prompts: bool = False,
        failure_text: str = FAILURE_TEXT,
    ) -> None:
        self.compiled = agent
        self.model = model
        self.settings = settings
        self.log_prompts = log_prompts  # 04 D3: sin él, los spans no llevan el texto
        self.failure_text = failure_text

    def run(
        self,
        context: dict[str, object],
        profile: Profile,
        history: list[HistoryMessage],
        reader: KbReader | None = None,
        deadline: datetime | None = None,
        toolset: AbstractToolset[None] | None = None,
    ) -> AgentOutput:
        """Una corrida de redactor (`draft`) o de agente de una sola llamada (`respond`); con
        `toolset`, puede llamar tools de negocio en la misma corrida (F2)."""
        instructions = instructions_for(self.compiled, profile)
        schema = self.compiled.output_schema
        with_evidence = schema in WITH_CLAIMS
        output_type = SCHEMAS[schema] if with_evidence else str
        started = time.perf_counter()
        try:
            result = self._execute(
                instructions.text, output_type, context, history, reader, toolset, deadline
            )
        except PolicyDenied as denied:
            return AgentOutput(
                text=self._failure_text(),
                variant=instructions.variant,
                failed=True,
                interventions=[str(denied)],
            )
        except Exception as exc:
            error_class = self._failure_class(exc)
            return AgentOutput(
                text=self._failure_text(),
                variant=instructions.variant,
                failed=True,
                error_class=error_class,
                outcome=self._failed(error_class, started),
            )
        output = result.output
        draft = output if isinstance(output, DraftWithEvidence) else DraftWithEvidence(text=str(output))
        return AgentOutput(
            text=draft.text,
            variant=instructions.variant,
            failed=False,
            messages=serialized(result.new_messages()),
            claims=list(draft.claims) if with_evidence else None,
            reads=list(reader.reads) if reader else [],
            step_target=draft.step_target if isinstance(draft, Respond) else None,
            usage=usage_of(result),
            outcome=self._outcome(result, started),
        )

    def decide(
        self,
        context: dict[str, object],
        profile: Profile,
        history: list[HistoryMessage],
        reader: KbReader | None = None,
        toolset: AbstractToolset[None] | None = None,
        deadline: datetime | None = None,
        steps: list[str] | None = None,
    ) -> DecisionOutput:
        """Salida tipada `TurnDecision@1`; si el modelo falla, el `fallback` del esquema (I5).

        Con `toolset`, el decisor llama las tools de negocio en la misma corrida: Pydantic AI valida
        sus argumentos, reintenta si no calzan y aplica el plazo de cada una. Con `steps`, un paso
        fuera de esa lista se le devuelve al modelo una vez para que elija otro; si insiste, la
        decisión sale igual y la guardia de transición la veta.
        """
        instructions = instructions_for(self.compiled, profile)
        started = time.perf_counter()
        validator = _step_validator(steps) if steps else None
        try:
            result = self._execute(
                instructions.text, TurnDecision, context, history, reader, toolset, deadline, validator
            )
        except PolicyDenied as denied:
            return DecisionOutput(decision=TurnDecision.fallback(), failed=True, interventions=[str(denied)])
        except Exception as exc:
            error_class = self._failure_class(exc)
            return DecisionOutput(
                decision=TurnDecision.fallback(), failed=True, outcome=self._failed(error_class, started)
            )
        messages = result.new_messages()
        return DecisionOutput(
            decision=result.output,
            failed=False,
            messages=serialized(messages),
            reads=list(reader.reads) if reader else [],
            tool_calls=_tool_calls(
                messages, exclude={f.__name__ for f in reader.functions()} if reader else set()
            ),
            usage=usage_of(result),
            outcome=self._outcome(result, started),
        )

    def review(
        self, context: dict[str, object], profile: Profile, deadline: datetime | None = None
    ) -> ReviewOutput:
        """`GateVerdict@1` sobre el borrador que trae `context`; sin historial ni tools. Si el modelo
        falla, el `fallback` del esquema, que rechaza: el borrador no sale sin revisar (I5)."""
        instructions = instructions_for(self.compiled, profile)
        started = time.perf_counter()
        try:
            result = self._execute(instructions.text, GateVerdict, context, [], None, None, deadline)
        except PolicyDenied as denied:
            return ReviewOutput(verdict=GateVerdict.fallback(), failed=True, interventions=[str(denied)])
        except Exception as exc:
            error_class = self._failure_class(exc)
            return ReviewOutput(
                verdict=GateVerdict.fallback(), failed=True, outcome=self._failed(error_class, started)
            )
        return ReviewOutput(
            verdict=result.output,
            failed=False,
            messages=serialized(result.new_messages()),
            usage=usage_of(result),
            outcome=self._outcome(result, started),
        )

    def _outcome(self, result: AgentRunResult[Any], started: float) -> RunOutcome:
        return outcome_of(result, _elapsed_ms(started), self.model.system, self.model.model_name)

    def _failed(self, error_class: str, started: float) -> RunOutcome:
        return failed_outcome(error_class, _elapsed_ms(started), self.model.system, self.model.model_name)

    def _failure_class(self, exc: Exception) -> str:
        """La clase del fallo. Un bug del runtime va al log como error, con su traza; una caída
        del proveedor, como aviso (F-18 de dev: lo uno no se disfraza de lo otro)."""
        error = classify(exc, self.model.system)
        if isinstance(error, InternalFault):
            log.error("agente %s: bug del runtime (%s)", self.compiled.role, error, exc_info=exc)
        else:
            log.warning("agente %s falló (%s): %s", self.compiled.role, type(error).__name__, error)
        return type(error).__name__

    def _execute(
        self,
        instructions: str,
        output_type: type[OutputT],
        context: dict[str, object],
        history: list[HistoryMessage],
        reader: KbReader | None,
        toolset: AbstractToolset[None] | None = None,
        deadline: datetime | None = None,
        validator: OutputValidator | None = None,
    ) -> AgentRunResult[OutputT]:
        """Una corrida con las capacidades del agente; `PolicyDenied` si una política la corta."""
        prior = _messages(history)
        agent = Agent(
            self.model,
            deps_type=type(None),
            instructions=instructions,
            output_type=output_type,
            model_settings=_within(self.settings, deadline),
            tools=reader.functions() if reader else [],
            toolsets=[toolset] if toolset is not None else [],
            capabilities=capabilities(
                self.compiled, context, reader is not None, len(prior), self.log_prompts
            ),
        )
        if validator is not None:
            agent.output_validator(validator)
        prompt = render_context(self.compiled, context)
        return agent.run_sync(prompt, message_history=prior, usage_limits=self._limits())

    def _limits(self) -> UsageLimits:
        """La primera petición no es una iteración con tools (05 §6.1, I6)."""
        return UsageLimits(request_limit=self.compiled.max_tool_iterations + 1)

    def _failure_text(self) -> str:
        return "" if self.compiled.on_failure == "open" else self.failure_text


OutputValidator = Callable[[RunContext[None], Any], Any]


def _step_validator(steps: list[str]) -> OutputValidator:
    """Devuelve al modelo un `step_target` que no está entre `steps` (con o sin el prefijo `Tipo:`),
    una sola vez: en el último intento la decisión pasa tal cual."""
    names = {step.rpartition(":")[2] for step in steps}

    def check(ctx: RunContext[None], decision: Any) -> Any:
        target = getattr(decision, "step_target", None)
        if not target or target.rpartition(":")[2] in names or ctx.retry >= ctx.max_retries:
            return decision
        raise ModelRetry(f"El paso {target} no es una transición permitida; elige uno de: {steps}.")

    return check


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _within(settings: ModelSettings | None, deadline: datetime | None) -> ModelSettings | None:
    """El plazo de cada petición al modelo no pasa del plazo del turno (06 D9)."""
    if deadline is None:
        return settings
    remaining = max((deadline - datetime.now(UTC)).total_seconds(), 0.1)
    current = (settings or {}).get("timeout")
    timeout = min(float(current), remaining) if isinstance(current, int | float) else remaining
    return {**(settings or {}), "timeout": timeout}


def _tool_calls(messages: list[ModelMessage], exclude: set[str]) -> list[ToolCallRequest]:
    """Las tools que llamó el agente en su corrida, sin las de lectura de KB y sin la de salida."""
    return [
        ToolCallRequest(name=part.tool_name, arguments=part.args_as_dict())
        for message in messages
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
        and part.tool_name not in exclude
        and not part.tool_name.startswith("final_result")
    ]


def serialized(messages: list[ModelMessage]) -> list[dict[str, object]]:
    """Mensajes de Pydantic AI como JSON; se leen de vuelta con `ModelMessagesTypeAdapter`."""
    return ModelMessagesTypeAdapter.dump_python(messages, mode="json")  # pyright: ignore[reportReturnType]


def _messages(history: list[HistoryMessage]) -> list[ModelMessage]:
    """El historial como mensajes de Pydantic AI; la ventana la aplica `history_window`.

    Termina en una respuesta: un mensaje final de la persona sin respuesta (un turno que falló) se
    omite, porque Pydantic AI le pegaría la pregunta nueva y la ventana ya no sabría dónde cortar.
    """
    while history and history[-1].role == "user":
        history = history[:-1]
    return [
        ModelRequest(parts=[UserPromptPart(m.text)])
        if m.role == "user"
        else ModelResponse(parts=[TextPart(m.text)])
        for m in history
    ]


def usage_of(result: AgentRunResult[Any]) -> RunUsageView:
    """Peticiones, tokens y costo de la corrida (04 §6.5); costo None si el precio no se conoce."""
    usage = result.usage
    try:
        cost = float(sum(m.cost().total_price for m in result.new_messages() if isinstance(m, ModelResponse)))
    except LookupError:
        cost = None
    return RunUsageView(
        requests=usage.requests,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_usd=cost,
    )


__all__ = ["AgentOutput", "AgentRunner", "DecisionOutput", "HistoryMessage", "LlmError", "RunUsageView"]
