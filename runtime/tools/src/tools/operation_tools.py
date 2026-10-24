"""Tools de alto nivel sobre las operaciones de 14 §6.7: la LLM llama por nombre, el runtime pone los IDs."""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

from tools.contract import Tool, ToolError, ToolResult
from tools.entity import EntityType
from tools.operations import Aggregate, personal_filters
from tools.primitives import Primitives, SemanticTool

Operation = Literal["read", "write", "aggregate"]
#: Fuentes de binding admitidas (14 §6.7); `state.<clave>` además de estas.
BINDING_SOURCES = ("context.subject", "context.session", "context.step")
STATE_PREFIX = "state."
SUBJECT = "subject"


class OperationConfigError(ValueError):
    """La declaración de una tool de operación no encaja con su entidad: error de arranque."""


class OperationSpec(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    operation: Operation
    entity: str
    inputs: list[str] = Field(default_factory=list[str], description="Campos que aporta la LLM.")
    where: dict[str, object] = Field(default_factory=dict[str, object], description="Filtros fijos.")
    bind: dict[str, str] = Field(
        default_factory=dict[str, str], description="Destino (subject, clave o campo) → fuente del contexto."
    )
    column: str | None = Field(default=None, description="Columna de `aggregate`.")
    fn: Aggregate | None = Field(default=None, description="Función de `aggregate`.")


class OperationTool(SemanticTool):
    """Base de las tools generadas; cada una es una subclase con su `name`, `description` y `Args`.

    Es una tool semántica declarada: fija filtros y valores sobre una primitiva `records.*`.
    """

    spec: ClassVar[OperationSpec]
    entity: ClassVar[EntityType]

    def run(self, p: Primitives, args: BaseModel) -> ToolResult:
        bound = _resolve(self.spec.bind, p.context.bindings)
        subject = bound.pop(SUBJECT, None)
        given = {k: v for k, v in args.model_dump().items() if v is not None}
        values = {**self.spec.where, **bound, **given}
        return ToolResult(data=self._run(p, values, None if subject is None else str(subject)))

    def _run(self, p: Primitives, values: dict[str, object], subject: str | None) -> dict[str, object]:
        spec, entity = self.spec, self.entity
        if spec.operation == "write":
            key = str(values.pop(self.entity.key))
            return {"row": p.records.write(entity, key, values, subject)}
        if spec.operation == "aggregate":
            return p.records.aggregate(entity, spec.column or "", spec.fn or "count", values, subject)
        rows = p.records.read(entity, values, subject)
        return {"rows": rows, "count": len(rows)}


def operation_tool(spec: OperationSpec, entity: EntityType) -> Tool:
    """La `Tool` de 03 para una declaración; valida contra la entidad o falla el arranque."""
    _validate(spec, entity)
    attributes: dict[str, Any] = {
        "name": spec.name,
        "description": spec.description,
        "Args": _args(spec, entity),
        "kind": "write" if spec.operation == "write" else "read",
        "spec": spec,
        "entity": entity,
        "reads": (entity.name,),
        "writes": (entity.name,) if spec.operation == "write" else (),
    }
    return type(f"OperationTool_{spec.name}", (OperationTool,), attributes)()


def _validate(spec: OperationSpec, entity: EntityType) -> None:
    columns = {entity.key, *entity.fields}
    problems = [f"{spec.name}: {p}" for p in _problems(spec, entity, columns)]
    if problems:
        raise OperationConfigError("; ".join(problems))


def _problems(spec: OperationSpec, entity: EntityType, columns: set[str]) -> list[str]:
    problems = [
        f"entidad {entity.name!r} no tiene {f!r}" for f in [*spec.inputs, *spec.where] if f not in columns
    ]
    problems += [f"bind a {t!r} fuera de la entidad" for t in spec.bind if t != SUBJECT and t not in columns]
    problems += [f"fuente de binding no admitida {s!r}" for s in spec.bind.values() if not _admitted(s)]
    problems += [
        f"{f!r} no puede venir de la LLM y del contexto (C6)" for f in set(spec.inputs) & set(spec.bind)
    ]
    if entity.subject_linked and SUBJECT not in spec.bind:
        problems.append(f"la entidad {entity.name!r} es del sujeto: falta bind subject")
    if spec.operation == "write" and entity.key not in {*spec.inputs, *spec.bind}:
        problems.append(f"write necesita la clave {entity.key!r} en inputs o bind")
    if spec.operation == "aggregate" and (spec.fn is None or spec.column not in entity.fields):
        problems.append("aggregate necesita fn y una columna de la entidad")
    if spec.operation != "write":
        filters = [*spec.inputs, *spec.where, *(t for t in spec.bind if t != SUBJECT)]
        problems += [
            f"no se filtra por el campo personal {f!r} (02)" for f in personal_filters(entity, filters)
        ]
    return problems


def _admitted(source: str) -> bool:
    return source in BINDING_SOURCES or (source.startswith(STATE_PREFIX) and len(source) > len(STATE_PREFIX))


def _args(spec: OperationSpec, entity: EntityType) -> type[BaseModel]:
    """Solo lo que aporta la LLM (C6); en lectura, cada input es un filtro opcional."""
    required = spec.operation == "write"
    fields: dict[str, Any] = {
        name: (entity.type_of(name), ...) if required else (entity.type_of(name) | None, None)
        for name in spec.inputs
    }
    return create_model(f"{spec.name}_args", __config__=ConfigDict(extra="forbid"), **fields)


def _resolve(bind: dict[str, str], available: dict[str, object]) -> dict[str, object]:
    missing = [source for source in bind.values() if available.get(source) is None]
    if missing:
        raise ToolError("not_found")
    return {target: available[source] for target, source in bind.items()}
