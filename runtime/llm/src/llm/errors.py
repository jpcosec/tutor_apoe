"""Errores tipados del sustrato (spec 04 §6.3).

Dos familias deciden el reintento: `LlmTransient` (saturación, plazo, red o 5xx) se reintenta
con espera; `LlmRejected` (credenciales, petición inválida) nunca. `LlmUnexpected` se reintenta
una sola vez. Salida inválida y límite de uso no se reintentan aquí: 05 aplica `on_failure`.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

import httpx
import yaml
from pydantic_ai.exceptions import AgentRunError, UnexpectedModelBehavior, UsageLimitExceeded

SATURATION = Path(__file__).with_name("saturation.yaml")


class LlmError(Exception):
    """Raíz de los errores del modelo de lenguaje."""


class LlmUnknownModel(LlmError):
    """El par no tiene capacidades declaradas o no tiene conformidad vigente (I2)."""


class LlmCapabilityMismatch(LlmError):
    """El agente pide una capacidad que el par del despliegue no tiene (04 §6.1)."""


class LlmTransient(LlmError):
    """Reintentable con espera (I5)."""


class LlmRateLimited(LlmTransient):
    """429 del proveedor."""


class LlmTimeout(LlmTransient):
    """El transporte no respondió a tiempo."""


class LlmUnavailable(LlmTransient):
    """408, 5xx o sin conexión."""


class LlmRejected(LlmError):
    """El proveedor rechazó la petición: reintentar no cambia nada."""


class LlmAuthError(LlmRejected):
    """401 o 403: credenciales."""


class LlmInvalidRequest(LlmRejected):
    """400 o 422: la petición está mal formada."""


class LlmOutputInvalid(LlmError):
    """El modelo agotó los reintentos de salida (I6)."""


class LlmUsageLimit(LlmError):
    """Se agotó el tope de peticiones de la corrida (05 I6)."""


class LlmUnexpected(LlmError):
    """Comportamiento no clasificado del sustrato: un reintento."""


class InternalFault(LlmError):
    """La excepción no vino del modelo ni del transporte: es un bug del runtime, no una caída del
    proveedor (F-18 de dev), y no se disfraza de una."""


def classify(exc: Exception, provider: str | None = None) -> LlmError:
    """De una excepción del sustrato o del transporte a su clase."""
    if isinstance(exc, LlmError):
        return exc
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return _by_status(status, exc)
    if saturated(str(getattr(exc, "body", "") or exc), provider):  # P6: 200 con cuerpo de saturación
        return LlmRateLimited(str(exc))
    if isinstance(exc, TimeoutError | httpx.TimeoutException):
        return LlmTimeout(str(exc))
    if isinstance(exc, ConnectionError | httpx.ConnectError):
        return LlmUnavailable(str(exc))
    if isinstance(exc, UsageLimitExceeded):
        return LlmUsageLimit(str(exc))
    message = str(exc).lower()
    if isinstance(exc, UnexpectedModelBehavior) and (
        "maximum retries" in message or "maximum output retries" in message
    ):
        return LlmOutputInvalid(str(exc))
    if isinstance(exc, UnexpectedModelBehavior | AgentRunError):
        return LlmUnexpected(str(exc))
    return InternalFault(f"{type(exc).__name__}: {exc}")


def _by_status(status: int, exc: Exception) -> LlmError:
    message = str(exc)
    if status in (401, 403):
        return LlmAuthError(message)
    if status in (400, 422):
        return LlmInvalidRequest(message)
    if status == 429:
        return LlmRateLimited(message)
    if status == 408 or status >= 500:
        return LlmUnavailable(message)
    return LlmRejected(message)


@cache
def _patterns() -> dict[str, list[re.Pattern[str]]]:
    raw: dict[str, list[str]] = yaml.safe_load(SATURATION.read_text(encoding="utf-8")) or {}
    return {name: [re.compile(p, re.IGNORECASE | re.DOTALL) for p in found] for name, found in raw.items()}


def saturated(body: str, provider: str | None = None) -> bool:
    """El cuerpo dice saturación según los patrones del proveedor o los comunes (P6)."""
    patterns = _patterns()
    candidates = [*patterns.get("*", []), *(patterns.get(provider, []) if provider else [])]
    return any(p.search(body) for p in candidates)
