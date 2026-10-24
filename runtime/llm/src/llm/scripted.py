"""`ScriptedModel`: doble de modelo con guion, sobre el `FunctionModel` del sustrato (spec 04 §7)."""

from __future__ import annotations

import json
from typing import Any, cast

from pydantic import BaseModel, Field
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel


class ScriptedStep(BaseModel):
    text: str = Field(description="Texto de la respuesta (obligatorio).")
    tool_calls: list[dict[str, object]] | None = Field(default=None, description="[{name, arguments}]")
    structured: dict[str, object] | None = Field(default=None, description="Salida tipada esperada.")


class ScriptedModel:
    """Reproduce los pasos en orden; un paso de más es `AssertionError`. Registra lo que recibió."""

    def __init__(self, steps: list[ScriptedStep]) -> None:
        self.steps = list(steps)
        self.received: list[list[ModelMessage]] = []
        self.instructions: list[str | None] = []
        self.model = FunctionModel(self._respond)

    def _respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        assert self.steps, "llamada al modelo fuera de guion"
        self.received.append(list(messages))
        self.instructions.append(info.instructions)
        step = self.steps.pop(0)
        if step.tool_calls:
            return ModelResponse(
                parts=[
                    ToolCallPart(str(c["name"]), cast("dict[str, Any] | None", c.get("arguments")))
                    for c in step.tool_calls
                ]
            )
        if step.structured is not None and info.output_tools:
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, step.structured)])
        if step.structured is not None:
            return ModelResponse(parts=[TextPart(json.dumps(step.structured, ensure_ascii=False))])
        return ModelResponse(parts=[TextPart(step.text)])
