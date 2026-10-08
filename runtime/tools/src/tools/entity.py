"""`EntityType`: un tipo de registro de negocio, sobre el que operan las operaciones de 14 §6.7."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ontology import OntologyObject, Ref

JsonType = Literal["string", "number", "integer", "boolean", "object", "array"]
PYTHON_TYPES: dict[str, type] = {
    "string": str,
    "number": float,
    "integer": int,
    "boolean": bool,
    "object": dict,
    "array": list,
}


class EpisodeSpec(BaseModel, frozen=True):
    """Una entidad cuyas filas son episodios del cliente: tienen un estado y estados que las cierran."""

    state_field: str = Field(description="Campo de la fila que lleva el estado.")
    closing: list[str] = Field(description="Estados que cierran el episodio.")


class EntityType(OntologyObject):
    """Se lee de un `EntityDoc` de la KB (15 O2, D1); la nombran las tools de operación."""

    schema_version: int = 1
    name: str
    key: str = Field(description="Campo clave; en el almacén es la clave del registro.")
    fields: dict[str, JsonType] = Field(description="Campo → tipo JSON; no incluye la clave.")
    personal_fields: frozenset[str] = Field(default=frozenset[str](), description="Van a la bóveda (02).")
    subject_linked: bool = Field(default=True, description="Cada registro pertenece a un sujeto.")
    descriptions: dict[str, str] = Field(default_factory=dict[str, str], description="Campo → qué significa.")
    episode: EpisodeSpec | None = Field(
        default=None, description="Si sus filas son episodios (la KB lo declara)."
    )

    @classmethod
    def declare(cls, name: str, key: str, fields: dict[str, JsonType], **extra: object) -> EntityType:
        return cls(ref=Ref(kind="entity", id=name), name=name, key=key, fields=fields, **extra)  # pyright: ignore[reportArgumentType]

    def type_of(self, field: str) -> type:
        """El tipo Python de un campo o de la clave; `KeyError` si la entidad no lo tiene."""
        if field == self.key:
            return str
        return PYTHON_TYPES[self.fields[field]]
