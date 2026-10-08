"""Conformidad de un par (spec 04 §8.3, I2, I9): las seis pruebas y su reporte.

Un par se usa en producción solo con reporte vigente: el archivo `conformance_reports/<provider>-<model>.json`
del módulo, con la versión del sustrato instalada y las seis pruebas en `ok`. Cambiar la versión
de Pydantic AI invalida todos los reportes. Fuera de producción, la falta es una advertencia.
La comprobación (`check_report`) la hace `make_model` al armar cada modelo; nadie más la llama.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models import Model

from llm.errors import LlmUnknownModel
from llm.settings import LlmSettings

log = logging.getLogger(__name__)
REPORTS = Path(__file__).with_name("conformance_reports")
PRODUCTION = frozenset({"prod", "production"})


class Check(BaseModel, frozen=True):
    name: str
    ok: bool
    detail: str = ""


class ConformanceReport(BaseModel, frozen=True):
    pair: str
    substrate_version: str
    created_at: datetime
    checks: list[Check] = Field(description="Las seis pruebas de 04 §8.3, en orden.")

    @property
    def conformant(self) -> bool:
        return len(self.checks) == len(CHECKS) and all(c.ok for c in self.checks)


class City(BaseModel):
    ciudad: str
    pais: str


class OpenMap(BaseModel):
    datos: dict[str, str] = Field(description="Pares libres nombre → valor.")


def substrate_version() -> str:
    """La distribución instalada de Pydantic AI (I9)."""
    for name in ("pydantic-ai-slim", "pydantic-ai"):
        try:
            return version(name)
        except PackageNotFoundError:
            continue
    return "desconocida"


def report_path(settings: LlmSettings, reports: Path = REPORTS) -> Path:
    return reports / f"{settings.provider}-{settings.model.replace('/', '_').replace(':', '_')}.json"


def run_conformance(settings: LlmSettings, model: Model) -> ConformanceReport:
    checks = [_run(name, check, model) for name, check in CHECKS.items()]
    return ConformanceReport(
        pair=settings.pair, substrate_version=substrate_version(), created_at=datetime.now(UTC), checks=checks
    )


def check_report(settings: LlmSettings, environ: Mapping[str, str], reports: Path = REPORTS) -> None:
    """I2: sin reporte vigente, error en producción y advertencia fuera de ella."""
    if settings.provider in ("test", "function"):
        return
    problem = report_problem(settings, reports)
    if problem is None:
        return
    if (environ.get("ENVIRONMENT") or environ.get("ENV") or "dev").strip().lower() in PRODUCTION:
        raise LlmUnknownModel(f"{settings.pair}: {problem}")
    log.warning("conformidad de %s: %s", settings.pair, problem)


def report_problem(settings: LlmSettings, reports: Path = REPORTS) -> str | None:
    """Por qué el par no tiene conformidad vigente, o None; `test` y `function` no la necesitan."""
    if settings.provider in ("test", "function"):
        return None
    path = report_path(settings, reports)
    if not path.is_file():
        return f"sin reporte ({path.name})"
    report = ConformanceReport.model_validate_json(path.read_text(encoding="utf-8"))
    if report.substrate_version != substrate_version():
        return f"reporte hecho con pydantic-ai {report.substrate_version}; instalado {substrate_version()}"
    if not report.conformant:
        return f"reporte no conforme: {[c.name for c in report.checks if not c.ok]}"
    return None


def _run(name: str, check: Callable[[Model], str | None], model: Model) -> Check:
    try:
        problem = check(model)
    except Exception as error:
        return Check(name=name, ok=False, detail=f"{type(error).__name__}: {error}"[:300])
    return Check(name=name, ok=problem is None, detail=problem or "")


def _last_response(messages: list[object]) -> ModelResponse:
    return next(m for m in reversed(messages) if isinstance(m, ModelResponse))


def _text(model: Model) -> str | None:
    result = Agent(model).run_sync("Responde solo con la palabra: hola")
    reason = _last_response(list(result.all_messages())).finish_reason
    return (
        None
        if result.output.strip() and reason in (None, "stop")
        else f"output={result.output!r} fin={reason}"
    )


def _tool(model: Model) -> str | None:
    calls: list[dict[str, int]] = []
    agent = Agent(model)

    @agent.tool_plain
    def sumar(a: int, b: int) -> int:  # pyright: ignore[reportUnusedFunction]
        """Suma dos enteros."""
        calls.append({"a": a, "b": b})
        return a + b

    agent.run_sync("¿Cuánto es 2 + 3? Usa la herramienta sumar.")
    return None if calls else "no llamó la tool"


def _structured(model: Model) -> str | None:
    output = Agent(model, output_type=City).run_sync("¿Dónde queda la Torre Eiffel?").output
    return None if output.ciudad and output.pais else f"salida vacía: {output}"


def _tools_and_structured(model: Model) -> str | None:
    agent = Agent(model, output_type=City)

    @agent.tool_plain
    def pais_de(ciudad: str) -> str:  # pyright: ignore[reportUnusedFunction]
        """El país de una ciudad."""
        return "Francia" if "par" in ciudad.lower() else "desconocido"

    output = agent.run_sync("Usa pais_de para saber el país de París y responde la estructura.").output
    return None if output.pais else f"salida vacía: {output}"


def _open_map(model: Model) -> str | None:
    Agent(model, output_type=OpenMap).run_sync("Devuelve en `datos` dos colores con su código hexadecimal.")
    return None


def _max_tokens(model: Model) -> str | None:
    result = Agent(model, model_settings={"max_tokens": 5}).run_sync("Cuenta del uno al cien, en palabras.")
    reason = _last_response(list(result.all_messages())).finish_reason
    return None if reason == "length" else f"fin={reason}"


CHECKS: dict[str, Callable[[Model], str | None]] = {
    "texto": _text,
    "tool": _tool,
    "salida_tipada": _structured,
    "tools_y_salida_tipada": _tools_and_structured,
    "mapa_abierto": _open_map,
    "max_tokens": _max_tokens,
}
