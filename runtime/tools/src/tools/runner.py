"""Catálogo y `ToolRunner` (spec 03 §6.1, §6.3).

Los agentes llaman las tools por el toolset de Pydantic AI (`tools.toolset`). `ToolRunner` queda
para lo que llega sin LLM (el aviso de estado de un canal): valida los argumentos y ejecuta.
"""

from __future__ import annotations

import logging
import time

from pydantic import ValidationError

from tools.contract import FieldError, Tool, ToolCall, ToolContext, ToolDeclaration, ToolOutcome
from tools.toolset import execute

log = logging.getLogger(__name__)


class ToolCatalog:
    def __init__(self, tools: list[Tool]) -> None:
        names = [t.name for t in tools]
        duplicated = {n for n in names if names.count(n) > 1}
        if duplicated:
            raise ValueError(f"tools repetidas: {sorted(duplicated)}")
        for tool in tools:  # 03 §4.1: `arg` de IdentityRequirement es un campo de Args
            required = type(tool).requires_identity
            if required is not None and required.arg not in type(tool).Args.model_fields:
                raise ValueError(f"{tool.name}: requires_identity.arg {required.arg!r} no está en Args")
        self._tools = {t.name: t for t in tools}

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def tools(self) -> list[Tool]:
        return [self._tools[name] for name in self.names()]

    def declarations(self, only: list[str] | None = None) -> list[ToolDeclaration]:
        wanted = self.names() if only is None else [n for n in only if n in self._tools]
        return [type(self._tools[n]).declaration() for n in wanted]


class ToolRunner:
    def __init__(self, catalog: ToolCatalog) -> None:
        self.catalog = catalog

    def run(self, call: ToolCall, context: ToolContext) -> ToolOutcome:
        started = time.perf_counter()
        outcome = self._run(call, context.model_copy(update={"call_id": call.call_id}))
        outcome = outcome.model_copy(update={"latency_ms": int((time.perf_counter() - started) * 1000)})
        log.info("tool %s → %s %s", call.name, outcome.status, outcome.error_class or "")
        return outcome

    def _run(self, call: ToolCall, context: ToolContext) -> ToolOutcome:
        tool = self.catalog.get(call.name)
        if tool is None:
            return ToolOutcome(call_id=call.call_id, name=call.name, status="unknown")  # 03 I2
        try:
            args = type(tool).Args.model_validate(call.arguments)
        except ValidationError as error:
            errors = [
                FieldError(field=".".join(map(str, e["loc"])), message=e["msg"]) for e in error.errors()
            ]
            return ToolOutcome(call_id=call.call_id, name=call.name, status="rejected", errors=errors)
        return execute(tool, context.model_copy(update={"call_id": call.call_id}), args)
