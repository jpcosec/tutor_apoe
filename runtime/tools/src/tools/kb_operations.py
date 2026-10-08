"""Las tools de operación que declara la KB (14 §6.7): un `ToolAtom` con `entity` es una operación."""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence

from kb import Document, KnowledgeBase
from tools.apis import ApiToolSpec, parse_parameters
from tools.event_tools import EventSpec
from tools.operation_tools import Operation, OperationConfigError, OperationSpec

TOOL_TAG = "type.knowledge.tool"
EVENT_TAG = "tool_kind.event"
EXTERNAL_TAG = "tool_kind.external"
KINDS: dict[str, Operation] = {
    "tool_kind.read": "read",
    "tool_kind.write": "write",
    "tool_kind.aggregate": "aggregate",
}


def operation_specs(kb: KnowledgeBase) -> list[OperationSpec]:
    """Una declaración por tool de la KB que nombra una entidad; las demás tienen código propio (03)."""
    documents = [d for d in kb.eligible() if TOOL_TAG in d.model_tags and d.payload.get("entity")]
    return [_spec(d) for d in documents]


def event_specs(kb: KnowledgeBase) -> list[EventSpec]:
    """Las tools de evento de la KB: `subject_events.create` con sus tipos cerrados."""
    documents = [d for d in kb.eligible() if TOOL_TAG in d.model_tags and EVENT_TAG in d.model_tags]
    return [
        EventSpec(
            name=str(d.payload.get("name") or ""),
            description=str(d.payload.get("description") or ""),
            kinds=[str(k) for k in _list(d.payload.get("kinds"))],
        )
        for d in documents
    ]


def api_specs(kb: KnowledgeBase, apis: Collection[str]) -> list[ApiToolSpec]:
    """Las tools de la KB sobre una API declarada: `provider` es la API y `endpoint` la operación.
    Una ficha externa cuyo `provider` no es una API declarada (p. ej. un proveedor que atiende una
    tool de código) no se toca."""
    documents = [
        d
        for d in kb.eligible()
        if TOOL_TAG in d.model_tags
        and EXTERNAL_TAG in d.model_tags
        and str(d.payload.get("provider")) in apis
    ]
    return [
        ApiToolSpec(
            name=str(d.payload.get("name") or _name_from_parameters(d)),
            description=str(d.payload.get("description") or ""),
            api=str(d.payload["provider"]),
            operation=str(d.payload.get("endpoint") or ""),
            parameters=parse_parameters(d.payload.get("parameters")),
        )
        for d in documents
    ]


def _name_from_parameters(document: Document) -> str:
    """El `name` del bloque `## Parameters`, o la clave del documento."""
    match = re.search(r'"name"\s*:\s*"([^"]+)"', str(document.payload.get("parameters") or ""))
    return match.group(1) if match else document.key


def _spec(document: Document) -> OperationSpec:
    payload = document.payload
    where: dict[str, object] = dict(_pairs(document, "where"))
    return OperationSpec(
        name=str(payload.get("name") or ""),
        description=str(payload.get("description") or ""),
        operation=_operation(document),
        entity=str(payload["entity"]),
        inputs=[str(i) for i in _list(payload.get("inputs"))],
        where=where,
        bind=_pairs(document, "bind"),
        column=_optional(payload.get("column")),
        fn=_optional(payload.get("fn")),  # pyright: ignore[reportArgumentType]
    )


def _operation(document: Document) -> Operation:
    for tag in document.model_tags:
        if tag in KINDS:
            return KINDS[tag]
    raise OperationConfigError(f"{document.key}: una tool con entity debe ser read, write o aggregate")


def _pairs(document: Document, field: str) -> dict[str, str]:
    """`[campo=valor, …]` de la KB como `dict`; una entrada sin `=` es error de arranque."""
    pairs: dict[str, str] = {}
    for item in _list(document.payload.get(field)):
        target, separator, value = str(item).partition("=")
        if not separator or not target.strip():
            raise OperationConfigError(f"{document.key}: {field} espera 'campo=valor', vino {item!r}")
        pairs[target.strip()] = value.strip()
    return pairs


def _list(value: object) -> Sequence[object]:
    return value if isinstance(value, list) else []  # pyright: ignore[reportUnknownVariableType]


def _optional(value: object) -> str | None:
    return str(value) if value else None
