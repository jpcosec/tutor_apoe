"""Tools de evento que declara la KB: la primitiva `subject_events.create` con sus tipos cerrados.

La KB nombra la tool y lista los tipos que la LLM puede registrar; el esquema que ve el modelo
los trae como `enum`, así un tipo inventado se rechaza antes de escribir.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

from tools.contract import Tool, ToolResult
from tools.primitives import Primitives, SemanticTool


class EventSpec(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    kinds: list[str] = Field(min_length=1, description="Tipos de evento que la LLM puede registrar.")


class EventTool(SemanticTool):
    spec: ClassVar[EventSpec]
    kind: ClassVar[Literal["read", "write", "external"]] = "write"

    def run(self, p: Primitives, args: BaseModel) -> ToolResult:
        values = args.model_dump()
        event_id = p.subject_events.create(str(values["kind"]), values["payload"], values["due_at"])
        return ToolResult(data={"event_id": event_id, "kind": values["kind"]})


def event_tool(spec: EventSpec) -> Tool:
    fields: dict[str, Any] = {
        "kind": (Literal[tuple(spec.kinds)], Field(description="Qué pasó.")),  # pyright: ignore[reportInvalidTypeForm]
        "payload": (
            dict[str, object],
            Field(default_factory=dict[str, object], description="Datos del evento."),
        ),
        "due_at": (datetime | None, Field(default=None, description="Cuándo volver a mirarlo.")),
    }
    args = create_model(f"{spec.name}_args", __config__=ConfigDict(extra="forbid"), **fields)
    attributes: dict[str, Any] = {
        "name": spec.name,
        "description": spec.description,
        "Args": args,
        "spec": spec,
    }
    return type(f"EventTool_{spec.name}", (EventTool,), attributes)()
