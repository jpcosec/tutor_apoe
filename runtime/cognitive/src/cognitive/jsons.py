"""Tipos JSON recursivos para el contrato canónico (api-canonica §contratos comunes).

Alias PEP 695: pyright los resuelve y pydantic los valida recursivamente.
"""

from __future__ import annotations

type JsonValue = (
    str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
)
"""Cualquier valor JSON; se valida/serializa recursivamente por pydantic."""

type JsonObject = dict[str, JsonValue]
"""Objeto JSON (mapa de claves a JsonValue)."""

type JsonArray = list[JsonValue]
"""Arreglo JSON."""
