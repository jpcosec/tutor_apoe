"""World: puertos neutrales de datos, externo y evidencia (api-canonica §firmas públicas)."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Literal, Protocol, runtime_checkable

from pydantic import Field

from cognitive._base import FrozenModel
from cognitive.events import ExternalReceipt, Observation
from cognitive.jsons import JsonObject, JsonValue
from cognitive.scope import AccessScope, Scope
from ontology import Ref

DataOperation = Literal["create", "update", "delete"]
ExternalKind = Literal["observe", "effect"]
RetryPolicy = Literal["never", "idempotent"]


class DataCommand(FrozenModel):
    """Comando de escritura a World.Data; updates/deletes exigen expected_revision."""

    operation: DataOperation
    entity: str
    key: str
    fields: JsonObject | None = None
    expected_revision: str | None = None
    scope: Scope


class EntitySchema(FrozenModel):
    """Esquema de entidad registrada; nada de tablas internas por nombre."""

    name: str
    key: str
    fields: dict[str, JsonValue] = Field(default_factory=dict)
    personal_fields: tuple[str, ...] = ()
    subject_linked: bool = False


EntityRegistry = Mapping[str, EntitySchema]


class ExternalOperation(FrozenModel):
    """Operación externa registrada; no se descubren operaciones arbitrarias."""

    name: str
    input_schema: JsonObject | None = None
    output_schema: JsonObject | None = None
    required_capabilities: frozenset[str] = frozenset()
    kind: ExternalKind
    timeout_seconds: int = 30
    retry_policy: RetryPolicy = "never"
    handler_version: str = "1"


@runtime_checkable
class WorldData(Protocol):
    """Acceso de solo entidades registradas; máquinas/bóveda no pasan por aquí."""

    def read(self, ref: Ref, access: AccessScope) -> Observation: ...
    def query(
        self, entity: str, filters: Mapping[str, JsonValue], access: AccessScope
    ) -> tuple[Observation, ...]: ...
    def write(self, command: DataCommand, access: AccessScope) -> Observation: ...
    def transaction(self) -> AbstractContextManager[WorldData]: ...


@runtime_checkable
class WorldExternal(Protocol):
    """Observación e invocación externa, siempre con receipt/provenance."""

    def observe(
        self, operation: str, args: Mapping[str, JsonValue], access: AccessScope
    ) -> Observation: ...
    def invoke(
        self, operation: str, args: Mapping[str, JsonValue], invocation_id: str, access: AccessScope
    ) -> ExternalReceipt: ...


@runtime_checkable
class ExternalAdapter(Protocol):
    """Implementación de una operación externa registrada."""

    def observe(
        self, operation: str, args: Mapping[str, JsonValue], access: AccessScope
    ) -> Observation: ...
    def invoke(
        self, operation: str, args: Mapping[str, JsonValue], invocation_id: str, access: AccessScope
    ) -> ExternalReceipt: ...
