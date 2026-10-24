"""Contrato de tool (spec 03 §4.1, §6.3, §7), en lo que la rebanada usa."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from ontology import Episode, OntologyObject, Ref

ErrorClass = Literal[
    "validation",
    "identity_not_verified",
    "timeout",
    "provider",
    "defect",
    "not_found",
    "conflict",
    "commit_failed",
    "forbidden",
    "in_progress",
]
Status = Literal["ok", "rejected", "error", "unknown"]


class ToolCall(BaseModel, frozen=True):
    call_id: str
    name: str
    arguments: dict[str, object] = Field(default_factory=dict[str, object])


class FieldError(BaseModel, frozen=True):
    field: str
    message: str


class ToolResult(BaseModel, frozen=True):
    data: dict[str, object] = Field(default_factory=dict[str, object], description="Vuelve al modelo.")
    message_for_user: str | None = Field(default=None, description="Texto que el sistema puede publicar.")
    audit: dict[str, object] = Field(default_factory=dict[str, object], description="Solo traza.")


class IdentityRequirement(BaseModel, frozen=True):
    """La tool exige que el sujeto tenga verificado un vínculo de este tipo (03 I5, 02 §6.2)."""

    kind: str = Field(description="Tipo de vínculo (canal o identificador), p. ej. `whatsapp`.")
    arg: str = Field(description="Campo de `Args` con el valor que el modelo afirma; solo se compara.")


class IdentityCheck(BaseModel, frozen=True):
    provided: bool = Field(description="El sujeto tiene un vínculo cargado de ese tipo.")
    verified: bool = Field(description="Lo afirmado coincide con lo cargado.")


class ToolOutcome(BaseModel, frozen=True):
    call_id: str
    name: str
    status: Status
    error_class: ErrorClass | None = None
    errors: list[FieldError] = Field(default_factory=list[FieldError])
    result: ToolResult | None = None
    latency_ms: int = 0
    deduplicated: bool = Field(default=False, description="Resultado de una llamada anterior (03 I7).")
    identity: IdentityCheck | None = Field(default=None, description="Con `requires_identity` (03 I5).")
    message_for_user: str | None = Field(default=None, description="El de un `ToolError` (03 §6.4).")
    retryable: bool = Field(default=False, description="Reintentar la misma llamada puede servir (03 §6.4).")

    def for_model(self) -> dict[str, object]:
        """Lo que vuelve al modelo (03 §6.3): siempre explica lo que pasó."""
        if self.status == "ok" and self.result is not None:
            return {
                "tool": self.name,
                "status": "ok",
                "message_for_user": self.result.message_for_user,
                **self.result.data,
            }
        return {
            "tool": self.name,
            "status": self.status,
            "error": self.error_class,
            "message_for_user": self.message_for_user,
            "retryable": self.retryable,
            "errors": [e.model_dump() for e in self.errors],
        }


class ToolContext(BaseModel, frozen=True):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    session_id: str
    turn_id: str
    call_id: str | None = Field(default=None, description="La llamada en curso; la pone el ToolRunner.")
    writes: tuple[str, ...] | None = Field(
        default=None, description="Entidades que la tool en curso declara escribir; None fuera del runner."
    )
    deadline: datetime | None = None
    ports: dict[str, Any] = Field(default_factory=dict[str, Any], description="Puertos de datos (02).")
    bindings: dict[str, object] = Field(
        default_factory=dict[str, object], description="Valores del contexto para `bind` (14 §6.7, C6)."
    )


class ToolCallEpisode(Episode):
    """Una llamada a tool como episodio: vive en su turno (o en el sujeto, si llegó sin turno)."""

    schema_version: int = 1
    name: str
    status: Status
    error_class: ErrorClass | None = None
    primitives: list[dict[str, object]] = Field(default_factory=list[dict[str, object]])


class ToolError(Exception):
    """Lo que una tool lanza para decir qué falló (03 §6.4); termina en `status = error`."""

    def __init__(
        self, error_class: ErrorClass, message_for_user: str | None = None, retryable: bool = False
    ) -> None:
        super().__init__(error_class)
        self.error_class: ErrorClass = error_class
        self.message_for_user = message_for_user
        self.retryable = retryable


class ProviderError(ToolError):
    """Falló el proveedor externo; por omisión vale reintentar."""

    def __init__(self, message_for_user: str | None = None, retryable: bool = True) -> None:
        super().__init__("provider", message_for_user, retryable)


class NotFound(ToolError):
    """El recurso pedido no existe."""

    def __init__(self, message_for_user: str | None = None) -> None:
        super().__init__("not_found", message_for_user)


class Conflict(ToolError):
    """El estado actual no admite la operación."""

    def __init__(self, message_for_user: str | None = None) -> None:
        super().__init__("conflict", message_for_user)


class ToolDeclaration(OntologyObject):
    """Lo que el modelo ve de una tool (13: ref = tool:<name>)."""

    schema_version: int = 1
    name: str
    description: str
    parameters: dict[str, object]


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    Args: ClassVar[type[BaseModel]]
    kind: ClassVar[Literal["read", "write", "external"]] = "read"
    timeout_seconds: ClassVar[float] = 5.0
    reads: ClassVar[tuple[str, ...]] = ()  # tipos de registro que consulta: sus lectores (02 R7)
    writes: ClassVar[tuple[str, ...]] = ()  # entidades que escribe; el agente que la llama las ve (16)
    idempotency_key: ClassVar[tuple[str, ...]] = ()  # campos de Args que identifican el efecto (03 I7)
    #: `subject`: una vez por clave y sujeto; `turn`: una vez por clave dentro del turno (o del evento
    #: del sujeto que la dispara), para efectos que la persona puede pedir de nuevo más tarde.
    idempotency_scope: ClassVar[Literal["subject", "turn"]] = "subject"
    requires_identity: ClassVar[IdentityRequirement | None] = None  # vínculo verificado (03 I5)

    @abstractmethod
    def execute(self, context: ToolContext, args: BaseModel) -> ToolResult: ...

    @classmethod
    def declaration(cls) -> ToolDeclaration:
        return ToolDeclaration(
            ref=Ref(kind="tool", id=cls.name),
            name=cls.name,
            description=cls.description,
            parameters=cls.Args.model_json_schema(),
        )
