"""Matriz de capacidades por par (spec 04; 10 D10: vive aquí y nadie la copia)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from llm.errors import LlmUnknownModel
from llm.settings import LlmSettings

CAPABILITIES_FILE = Path(__file__).with_name("capabilities.yaml")


class Capabilities(BaseModel, frozen=True):
    tools: bool = Field(description="Llamadas a herramientas.")
    structured_output: bool = Field(description="Salida tipada.")
    output_mode: Literal["tool", "native", "prompted"] = Field(description="Cómo se pide la salida tipada.")
    system_prompt: bool = Field(description="Respeta el rol system; si no, va como user.")
    usage_reported: bool = Field(description="El proveedor reporta tokens.")


def capabilities_of(settings: LlmSettings, path: Path = CAPABILITIES_FILE) -> Capabilities:
    """Clave exacta `provider|model`; si no, `provider|*`; si tampoco, `LlmUnknownModel`."""
    table: dict[str, dict[str, object]] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for key in (settings.pair, f"{settings.provider}|*"):
        if key in table:
            return Capabilities.model_validate(table[key])
    raise LlmUnknownModel(f"sin capacidades declaradas para {settings.pair}")
