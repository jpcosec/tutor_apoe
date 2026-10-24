"""Primitivas del runtime (03): la infraestructura que componen las tools semánticas.

Una primitiva es genérica y no sabe nada del negocio: escribir una fila de una entidad, crear un
evento del sujeto, enviar un mensaje. La LLM nunca la llama directo: la alcanza una tool
semántica, declarada en la KB o escrita como handler en el paquete del cliente. Cada llamada
queda en `Primitives.calls`, que la tool deja en su traza.
"""

from __future__ import annotations

import logging
from abc import abstractmethod
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal, Protocol, cast

from pydantic import BaseModel

from tools.contract import Tool, ToolContext, ToolError, ToolResult
from tools.entity import EntityType
from tools.operations import Aggregate, RecordsPort, aggregate, read, write

log = logging.getLogger(__name__)
SUBJECT_BINDING = "context.subject"


class PrimitiveCall(BaseModel, frozen=True):
    """Una primitiva que ejecutó una tool: lo que queda en la traza, sin los valores."""

    primitive: str
    target: str
    status: Literal["ok", "error"]


class SubjectEventsPort(Protocol):
    def add_event(
        self,
        session_id: str,
        kind: str,
        payload: dict[str, object],
        due_at: datetime | None,
        opened_by: str | None = None,
    ) -> int: ...
    def set_event_status(self, event_id: int, status: str) -> None: ...


class IdentitiesPort(Protocol):
    """Las identidades de canal del sujeto (02 §6.1): viven en la bóveda."""

    def address_of(self, subject_key: str, channel: str) -> str | None: ...


class MessagesPort(Protocol):
    """Un canal de salida (Twilio u otro): devuelve la referencia del proveedor."""

    def send(self, to: str, content_sid: str, content_variables: str) -> str: ...


class Primitives:
    """Las primitivas para una llamada a tool, sobre los puertos de su contexto."""

    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.calls: list[PrimitiveCall] = []
        self.records = Records(self)
        self.subject_events = SubjectEvents(self)
        self.messages = Messages(self)
        self.api = Api(self)

    @property
    def cause(self) -> str | None:
        """La llamada en curso como ref textual: lo que abre o cierra un episodio del cliente."""
        return f"tool_call:{self.context.call_id}" if self.context.call_id else None

    @property
    def subject(self) -> str:
        """El sujeto de la llamada, resuelto por el runtime; nunca lo aporta la LLM (14 C6)."""
        return str(self.context.bindings.get(SUBJECT_BINDING) or self.context.session_id)

    def has(self, name: str) -> bool:
        """Si el despliegue trae ese puerto (un paso opcional de la tool)."""
        return self.context.ports.get(name) is not None

    def port(self, name: str) -> Any:
        """Un puerto del contexto; sin él la tool no puede cumplir (defecto de despliegue)."""
        found = self.context.ports.get(name)
        if found is None:
            raise ToolError("defect")
        return found

    def record(self, primitive: str, target: str, status: Literal["ok", "error"] = "ok") -> None:
        self.calls.append(PrimitiveCall(primitive=primitive, target=target, status=status))


class Api:
    """`api.call`: una operación declarada de una API de terceros (pendientes F3).

    El adaptador del puerto `apis` valida contra la declaración de `client.yaml` y tipa los
    errores (`NotFound`, `Conflict`, `ProviderError`, `ToolError("validation")`); acá queda la
    auditoría: qué API y qué operación, con su estado, nunca los cuerpos."""

    def __init__(self, primitives: Primitives) -> None:
        self._p = primitives

    def call(
        self,
        api: str,
        operation: str,
        params: Mapping[str, object] | None = None,
        body: Mapping[str, object] | None = None,
    ) -> object:
        port = self._p.port("apis")
        target = f"{api}.{operation}"
        try:
            result = port.call(api, operation, dict(params or {}), dict(body) if body is not None else None)
        except Exception:
            self._p.record("api.call", target, "error")
            raise
        self._p.record("api.call", target)
        return result


class Records:
    """`records.read`, `records.write`, `records.aggregate` sobre las entidades de la KB."""

    def __init__(self, primitives: Primitives) -> None:
        self._p = primitives

    def entity(self, entity: str | EntityType) -> EntityType:
        """La entidad por nombre (del puerto `entities`, que arma la Ontology desde la KB)."""
        if isinstance(entity, EntityType):
            return entity
        entities = cast(dict[str, EntityType], self._p.port("entities"))
        if entity not in entities:
            raise ToolError("defect")
        return entities[entity]

    def read(
        self,
        entity: str | EntityType,
        where: Mapping[str, object] | None = None,
        subject: str | None = None,
        newest_first: bool = False,
    ) -> list[dict[str, object]]:
        """Todas las filas que cumplen el filtro (14 C7); nunca elige una en silencio."""
        declared = self.entity(entity)
        rows = read(self._port(), declared, dict(where or {}), subject, newest_first)
        self._p.record("records.read", declared.name)
        return rows

    def write(
        self, entity: str | EntityType, key: str, fields: Mapping[str, object], subject: str | None = None
    ) -> dict[str, object]:
        """Crea o actualiza la fila de la clave sin pisar lo que no viene (idempotente)."""
        declared = self.entity(entity)
        allowed = self._p.context.writes
        if allowed is not None and declared.name not in allowed:
            log.error("la tool escribe %s sin declararlo en writes (16)", declared.name)
            raise ToolError("forbidden")
        row = write(self._port(), declared, key, dict(fields), subject)
        if declared.episode is not None:
            self._mark(declared, key, row)
        self._p.record("records.write", f"{declared.name}:{key}")
        return row

    def _mark(self, entity: EntityType, key: str, row: Mapping[str, object]) -> None:
        """Fila de un episodio del cliente: la llamada que la crea la abre; un estado de cierre la cierra."""
        spec, cause = entity.episode, self._p.cause
        if spec is None or cause is None:
            return
        closes = str(row.get(spec.state_field) or "") in spec.closing
        port = self._p.port("records")
        port.mark_episode(
            entity.name,
            key,
            opened_by=cause if row.get("created") else None,
            closed_by=cause if closes else None,
        )

    def aggregate(
        self,
        entity: str | EntityType,
        column: str,
        fn: Aggregate,
        where: Mapping[str, object] | None = None,
        subject: str | None = None,
    ) -> dict[str, object]:
        declared = self.entity(entity)
        value = aggregate(self._port(), declared, column, fn, dict(where or {}), subject)
        self._p.record("records.aggregate", f"{declared.name}.{column}")
        return value

    def _port(self) -> RecordsPort:
        port: RecordsPort = self._p.port("records")
        return port


class SubjectEvents:
    """`subject_events.create` y `subject_events.set_status` (02 §6.4, 08 §6.8)."""

    def __init__(self, primitives: Primitives) -> None:
        self._p = primitives

    def create(
        self, kind: str, payload: Mapping[str, object] | None = None, due_at: datetime | None = None
    ) -> int:
        port: SubjectEventsPort = self._p.port("subject_events")
        event_id = port.add_event(self._p.subject, kind, dict(payload or {}), due_at, self._p.cause)
        self._p.record("subject_events.create", kind)
        return event_id

    def set_status(self, event_id: int, status: Literal["done", "cancelled"]) -> None:
        port: SubjectEventsPort = self._p.port("subject_events")
        port.set_event_status(event_id, status)
        self._p.record("subject_events.set_status", str(event_id))


class Messages:
    """`messages.send`: un mensaje o template por el canal de salida del despliegue."""

    def __init__(self, primitives: Primitives) -> None:
        self._p = primitives

    def address(self, channel: str) -> str | None:
        """Dónde escribirle al sujeto por ese canal, desde su identidad; None si no tiene una."""
        if not self._p.has("subjects"):
            return None
        identities: IdentitiesPort = self._p.port("subjects")
        found = identities.address_of(self._p.subject, channel)
        self._p.record("messages.address", channel)
        return found

    def send(self, to: str, content_sid: str, content_variables: str) -> str:
        port: MessagesPort = self._p.port("messages")
        try:
            reference = port.send(to, content_sid, content_variables)
        except Exception as error:
            self._p.record("messages.send", content_sid, "error")
            raise ToolError("provider") from error
        self._p.record("messages.send", content_sid)
        return reference


class SemanticTool(Tool):
    """Una tool que la LLM ve y que solo compone primitivas; su traza lista las que ejecutó."""

    def execute(self, context: ToolContext, args: BaseModel) -> ToolResult:
        primitives = Primitives(context)
        result = self.run(primitives, args)
        audit = {**result.audit, "primitives": _dump(primitives.calls)}
        return result.model_copy(update={"audit": audit})

    @abstractmethod
    def run(self, p: Primitives, args: BaseModel) -> ToolResult: ...


def _dump(calls: Sequence[PrimitiveCall]) -> list[dict[str, object]]:
    return [call.model_dump() for call in calls]
