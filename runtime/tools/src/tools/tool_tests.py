"""Las pruebas de tool que declara la KB (01 §4.6, documento 2 §8), ejecutadas por el `ToolRunner`."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from pydantic import BaseModel, Field

from kb import KnowledgeBase
from tools.contract import ToolCall, ToolContext, ToolOutcome
from tools.runner import ToolRunner

TOOL_TEST_TAG = "type.kb.tool_test"
Fixture = Callable[[], ToolContext]


class ToolTestCase(BaseModel, frozen=True):
    name: str
    tool: str
    fixture: str | None = Field(description="Estado sembrado que la prueba necesita; lo aporta el paquete.")
    args: dict[str, object]
    expect: dict[str, object]


class ToolTestResult(BaseModel, frozen=True):
    name: str
    passed: bool
    problems: list[str] = Field(default_factory=list[str])


def tool_test_cases(kb: KnowledgeBase) -> list[ToolTestCase]:
    documents = [d for d in kb.eligible() if TOOL_TEST_TAG in d.model_tags]
    return [
        ToolTestCase(
            name=d.name,
            tool=str(d.payload["tool"]),
            fixture=cast(str | None, d.payload.get("fixture")),
            args=cast(dict[str, object], d.payload.get("args") or {}),
            expect=cast(dict[str, object], d.payload.get("expect") or {}),
        )
        for d in documents
    ]


def run_tool_test(case: ToolTestCase, runner: ToolRunner, fixtures: dict[str, Fixture]) -> ToolTestResult:
    if case.fixture is not None and case.fixture not in fixtures:
        return ToolTestResult(
            name=case.name, passed=False, problems=[f"fixture desconocida {case.fixture!r}"]
        )
    context = fixtures[case.fixture]() if case.fixture else ToolContext(session_id="tool-test", turn_id="t")
    outcome = runner.run(ToolCall(call_id=case.name, name=case.tool, arguments=case.args), context)
    problems = mismatches(case.expect, observed(outcome))
    return ToolTestResult(name=case.name, passed=not problems, problems=problems)


def observed(outcome: ToolOutcome) -> dict[str, object]:
    """Lo que `expect` puede comparar: estado, clase de error y los datos del resultado."""
    return {
        "status": outcome.status,
        "error_class": outcome.error_class,
        "result": outcome.result.data if outcome.result else {},
    }


def mismatches(expected: object, actual: object, path: str = "") -> list[str]:
    """`expected` es un subconjunto de `actual`: cada clave esperada, con el mismo valor."""
    if isinstance(expected, dict):
        found = cast(dict[str, Any], actual) if isinstance(actual, dict) else {}
        pairs = cast(dict[str, object], expected).items()
        return [p for key, value in pairs for p in mismatches(value, found.get(key), f"{path}{key}.")]
    if expected != actual:
        return [f"{path.rstrip('.')}: se esperaba {expected!r}, vino {actual!r}"]
    return []
