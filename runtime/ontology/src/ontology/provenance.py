"""Procedencia de un objeto: quién lo creó, cuándo y desde qué release (spec 13 §6)."""

from __future__ import annotations

from datetime import UTC
from typing import Literal

from pydantic import AwareDatetime, BaseModel, field_validator


class Provenance(BaseModel, frozen=True):
    created_by: str
    created_at: AwareDatetime
    release_id: str | None = None
    origin: Literal["authored", "runtime", "derived"]

    @field_validator("created_at")
    @classmethod
    def _to_utc(cls, value: AwareDatetime) -> AwareDatetime:
        return value.astimezone(UTC)
