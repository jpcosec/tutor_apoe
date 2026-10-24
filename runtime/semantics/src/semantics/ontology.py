"""`Ontology`: el único lugar que responde, para cualquier `Ref`, qué es y cómo se ve (spec 15)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from functools import cached_property
from typing import Any, Protocol, cast

from pydantic import BaseModel, Field

from kb import KnowledgeBase, cell, contract_hash, render_view
from ontology import Ref
from semantics.entities import entity_documents, entity_type
from semantics.views import (
    ACTION_VIEW,
    DATA_VIEW,
    ERRORS_VIEW,
    PROFILE_VIEW,
    STATIC_VIEWS,
    TRACE_VIEW,
    rows_view,
)
from tools import (
    EntityType,
    OperationConfigError,
    Tool,
    event_specs,
    event_tool,
    operation_specs,
    operation_tool,
)

#: Lo que el resultado de una tool trae además de sus datos (03 §6.3).
FRAME = ("tool", "status", "message_for_user", "error", "errors", "rows")


class UnknownRef(KeyError):
    """La ref no es de una familia que la ontología resuelve, o no existe (15 O4)."""


class Resolved(BaseModel, frozen=True):
    ref: Ref
    text: str = Field(description="Cómo se ve para un agente.")
    data: dict[str, object] = Field(description="El objeto, serializable a JSON.")


class TurnSummaryLike(Protocol):
    @property
    def turn(self) -> int: ...
    @property
    def question(self) -> str: ...
    @property
    def step_before(self) -> str | None: ...
    @property
    def step_after(self) -> str | None: ...
    @property
    def decision(self) -> str | None: ...
    @property
    def tool(self) -> dict[str, object] | None: ...


class Ontology:
    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb

    @cached_property
    def _entities(self) -> dict[str, EntityType]:
        return {e.name: e for e in (entity_type(d) for d in entity_documents(self.kb))}

    @cached_property
    def _specs(self) -> dict[str, Any]:
        return {spec.name: spec for spec in operation_specs(self.kb)}

    @cached_property
    def fingerprint(self) -> str:
        """La KB (con entidades y tools) más el contrato de cada vista (15 O3)."""
        views = [*STATIC_VIEWS, *(rows_view(e) for e in self.entities())]
        contracts = sorted(contract_hash(view) for view in views)
        return hashlib.sha256(json.dumps([self.kb.fingerprint, contracts]).encode()).hexdigest()

    def entities(self) -> list[EntityType]:
        return [self._entities[name] for name in sorted(self._entities)]

    def entity(self, name: str) -> EntityType:
        return self._entities[name]

    def personal_fields(self) -> dict[str, frozenset[str]]:
        return {e.name: e.personal_fields for e in self.entities() if e.personal_fields}

    def operation_tools(self) -> list[Tool]:
        """Las tools de operación de la KB, validadas contra sus entidades (15 O5)."""
        unknown = sorted({s.entity for s in self._specs.values()} - set(self._entities))
        if unknown:
            raise OperationConfigError(f"tools de la KB sobre entidades no declaradas: {unknown}")
        return [operation_tool(spec, self._entities[spec.entity]) for spec in self._specs.values()]

    def declared_tools(self) -> list[Tool]:
        """Todas las tools semánticas que declara la KB: de operación y de evento (03, 15 O5)."""
        return [*self.operation_tools(), *(event_tool(spec) for spec in event_specs(self.kb))]

    def entity_map(self) -> dict[str, EntityType]:
        """Las entidades por nombre: el puerto `entities` de las primitivas `records.*`."""
        return dict(self._entities)

    def render_tool_result(self, outcome: dict[str, object]) -> str:
        """Tool y estado, filas con la vista de su entidad, el resto de los datos y los errores (15 §6.1)."""
        action = [
            {"campo": k, "valor": cell(outcome.get(k))} for k in FRAME[:4] if outcome.get(k) is not None
        ]
        if (ref := tool_ref(outcome)) is not None:
            action.append({"campo": "ref", "valor": ref})
        parts = [
            render_view(ACTION_VIEW, action) if action else "",
            self._rows(outcome),
            self._data(outcome),
            self._errors(outcome),
        ]
        return "\n\n".join(part for part in parts if part)

    def citable(self, outcome: dict[str, object] | None) -> set[str]:
        """Lo que un resultado de tool vuelve citable en el turno (06 E2): la acción misma si salió
        bien (`tool:<nombre>`) y, si es de operación, cada fila (`record:<entidad>:<clave>`)."""
        if outcome is None:
            return set()
        action = {ref} if (ref := tool_ref(outcome)) is not None else set[str]()
        spec = self._specs.get(str(outcome.get("tool")))
        if spec is None or spec.entity not in self._entities:
            return action
        rows = cast(list[dict[str, object]], outcome.get("rows") or [])
        refs = (record_ref(self._entities[spec.entity], row) for row in rows)
        return action | {ref for ref in refs if ref}

    def render_profile(self, ficha: dict[str, object]) -> str:
        rows = [{"dato": k, "valor": cell(v)} for k, v in ficha.items() if v is not None]
        return render_view(PROFILE_VIEW, rows) if rows else ""

    def render_trace(self, summaries: Sequence[TurnSummaryLike]) -> str:
        rows = [_trace_row(s) for s in summaries]
        return render_view(TRACE_VIEW, rows) if rows else ""

    def resolve(self, ref: Ref) -> Resolved:
        """Un átomo, una entidad o una tool, con su texto (15 O4)."""
        try:
            return self._resolve(ref)
        except KeyError as error:
            raise UnknownRef(str(ref)) from error

    def search(self, query: str, k: int = 8) -> list[Any]:
        return self.kb.rank(query, k)

    def _resolve(self, ref: Ref) -> Resolved:
        if ref.kind == "kb":
            document = self.kb.get(ref.id)
            return Resolved(ref=ref, text=self.kb.render(ref.id), data=dict(document.payload))
        if ref.kind == "entity":
            entity = self._entities[ref.id]
            document = next(d for d in entity_documents(self.kb) if d.payload.get("name") == ref.id)
            return Resolved(ref=ref, text=self.kb.render(document.key), data=entity.model_dump(mode="json"))
        if ref.kind == "tool":
            spec = self._specs[ref.id]
            return Resolved(
                ref=ref, text=f"{spec.name}: {spec.description}", data=spec.model_dump(mode="json")
            )
        raise KeyError(ref.kind)

    def _rows(self, outcome: dict[str, object]) -> str:
        spec = self._specs.get(str(outcome.get("tool")))
        rows = cast(list[dict[str, object]], outcome.get("rows") or [])
        if spec is None or spec.entity not in self._entities or "rows" not in outcome:
            return ""
        entity = self._entities[spec.entity]
        columns = [entity.key, *entity.fields]
        table = [
            {"ref": record_ref(entity, row) or "", **{c: cell(row.get(c)) for c in columns}} for row in rows
        ]
        return render_view(rows_view(entity), table)

    def _data(self, outcome: dict[str, object]) -> str:
        known = FRAME if outcome.get("tool") in self._specs else FRAME[:5]
        rows = [
            {"campo": k, "valor": cell(v)} for k, v in outcome.items() if k not in known and v is not None
        ]
        return render_view(DATA_VIEW, rows) if rows else ""

    def _errors(self, outcome: dict[str, object]) -> str:
        errors = cast(list[dict[str, object]], outcome.get("errors") or [])
        rows = [{"campo": cell(e.get("field")), "problema": cell(e.get("message"))} for e in errors]
        return render_view(ERRORS_VIEW, rows) if rows else ""


def tool_ref(outcome: dict[str, object]) -> str | None:
    """`tool:<nombre>` para un resultado exitoso; un rechazo o un error no respaldan nada."""
    if outcome.get("status") != "ok":
        return None
    try:
        return str(Ref(kind="tool", id=str(outcome.get("tool"))))
    except ValueError:
        return None


def record_ref(entity: EntityType, row: dict[str, object]) -> str | None:
    """`record:<entidad>:<clave>`, o None si la clave no cumple la gramática de refs (13 §4.0)."""
    try:
        return str(Ref(kind="record", id=f"{entity.name}:{row.get(entity.key)}"))
    except ValueError:
        return None


def _trace_row(summary: TurnSummaryLike) -> dict[str, str]:
    tool = summary.tool or {}
    return {
        "turno": str(summary.turn),
        "mensaje": cell(summary.question),
        "paso": f"{summary.step_before or '—'} → {summary.step_after or '—'}",
        "decision": cell(summary.decision),
        "tool": f"{tool.get('tool')} → {tool.get('status')}" if tool else "",
    }
