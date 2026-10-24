"""Módulo 04: el modelo de lenguaje sobre Pydantic AI. Su interfaz tiene tres audiencias; cada
bloque de `__all__` dice cuál es la suya."""

from llm.capabilities import Capabilities, capabilities_of
from llm.conformance import ConformanceReport, report_path, report_problem, run_conformance
from llm.errors import (
    InternalFault,
    LlmAuthError,
    LlmCapabilityMismatch,
    LlmError,
    LlmInvalidRequest,
    LlmOutputInvalid,
    LlmRateLimited,
    LlmRejected,
    LlmTimeout,
    LlmTransient,
    LlmUnavailable,
    LlmUnexpected,
    LlmUnknownModel,
    LlmUsageLimit,
    classify,
)
from llm.factory import make_model, model_settings, settings_from_env
from llm.outcome import Attempts, FinishReason, RunOutcome, failed_outcome, outcome_of
from llm.scripted import ScriptedModel, ScriptedStep
from llm.settings import LlmSettings

# El ensamblaje: armar el modelo del despliegue y certificar el par (04 §6.1–§6.3, I2).
__all__ = [
    "Capabilities",
    "ConformanceReport",
    "LlmSettings",
    "capabilities_of",
    "make_model",
    "model_settings",
    "report_path",
    "report_problem",
    "run_conformance",
    "settings_from_env",
]
# Quien corre un agente: cómo terminó la corrida y qué falló (04 §6.4, taxonomía de errores).
__all__ += [
    "Attempts",
    "FinishReason",
    "InternalFault",
    "LlmAuthError",
    "LlmCapabilityMismatch",
    "LlmError",
    "LlmInvalidRequest",
    "LlmOutputInvalid",
    "LlmRateLimited",
    "LlmRejected",
    "LlmTimeout",
    "LlmTransient",
    "LlmUnavailable",
    "LlmUnexpected",
    "LlmUnknownModel",
    "LlmUsageLimit",
    "RunOutcome",
    "classify",
    "failed_outcome",
    "outcome_of",
]
# Las pruebas: un modelo guionado en lugar del proveedor (04 §8).
__all__ += [
    "ScriptedModel",
    "ScriptedStep",
]
