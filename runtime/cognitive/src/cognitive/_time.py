"""Tiempos UTC del contrato canónico.

`Utc` normaliza determinísticamente: naive se interpreta como UTC (sin salto),
offsets se convierten a UTC; el resultado siempre es datetime aware UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BeforeValidator


def _normalize_utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        # Campo requerido con None explícito: devolver None para que pydantic
        # reporte un ValidationError limpio (campo requerido), nunca AttributeError.
        return None
    parsed = (
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, str)
        else value
    )
    if parsed.tzinfo is None:
        # Naive se interpreta como UTC (documentado); no se añade información.
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


type Utc = Annotated[datetime, BeforeValidator(_normalize_utc)]
"""datetime aware UTC; naive se normaliza a UTC, offsets se convierten."""
