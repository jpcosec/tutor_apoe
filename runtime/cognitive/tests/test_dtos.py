"""Smoke de DTOs del contrato canónico: congelados, extra=forbid, copia defensiva."""

from __future__ import annotations

from copy import copy, deepcopy
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic import ValidationError

from cognitive import (
    ContextSnapshot,
    Event,
    FrozenModel,
    GuardExpr,
    JsonValue,
    MachineCommand,
    MachineDefinition,
    MachineGraph,
    MachineGraphDoc,
    MachineInstance,
    Scope,
    StateDefinition,
    TransitionDecision,
    ValueBinding,
    machine_definition_hash,
    machine_definition_payload,
)
from ontology import Ref

DEF = Ref.parse("kb:Machine:m1@rel-1")
MI1 = Ref.parse("machine_instance:m-1")
T0 = datetime(2026, 10, 5, 0, 0, 0)


def _instance(state: str = "open", revision: int = 0) -> MachineInstance:
    return MachineInstance(
        ref=MI1,
        definition_ref=DEF,
        definition_hash="h1",
        release_id="rel-1",
        owner_ref=Ref.parse("subject:s-1"),
        scope=Scope(client_id="c1", subject_ref=Ref.parse("subject:s-1")),
        state=state,
        revision=revision,
        created_at=T0,
        updated_at=T0,
    )


def test_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        MachineInstance(
            ref=MI1,
            definition_ref=DEF,
            definition_hash="h1",
            release_id="rel-1",
            owner_ref=Ref.parse("subject:s-1"),
            scope=Scope(client_id="c1"),
            state="open",
            created_at=T0,
            updated_at=T0,
            sorpresa=True,  # type: ignore[call-arg]
        )


def test_frozen_no_mutacion() -> None:
    inst = _instance()
    with pytest.raises(ValidationError):
        inst.state = "closed"  # type: ignore[misc]


def test_copia_defensiva_dicts() -> None:
    schemas: dict[str, JsonValue] = {"event:1": {"type": "object"}}
    definition = MachineDefinition(
        ref=DEF, version="1", content_hash="c", family="f", initial_state="open",
        states=(), transitions=(), event_schemas=schemas,
    )
    cast(dict[str, Any], schemas["event:1"])["extra"] = True
    assert definition.event_schemas == {"event:1": {"type": "object"}}


def test_guard_validacion() -> None:
    g = GuardExpr(op="eq", path=("world", "x"), value={"allowed": True})
    value = cast(dict[str, Any], g.value)
    with pytest.raises(TypeError):
        value["allowed"] = False
    nested = GuardExpr(op="eq", path=("a",), value={"n": {"m": [1, 2]}})
    nested_value = cast(dict[str, Any], nested.value)
    with pytest.raises(TypeError):
        nested_value["n"]["m"] = [3]
    with pytest.raises(TypeError):
        cast(list[Any], nested_value["n"]["m"]).append(9)
    GuardExpr(op="eq", path=("world", "x"), value=1)
    GuardExpr(op="exists", path=("world", "x"))
    GuardExpr(op="all", children=(GuardExpr(op="exists", path=("a",)),))
    GuardExpr(op="not", children=(GuardExpr(op="exists", path=("a",)),))
    with pytest.raises(ValidationError):
        GuardExpr(op="eq", path=("world", "x"))  # sin value
    with pytest.raises(ValidationError):
        GuardExpr(op="exists", path=("world", "x"), value=True)
    with pytest.raises(ValidationError):
        GuardExpr(op="any", children=())
    with pytest.raises(ValidationError):
        GuardExpr(op="not", children=())


def test_inmutabilidad_deepcopy_y_copy() -> None:
    expr = GuardExpr(op="eq", path=("world", "x"), value={"v": [1]})
    value = cast(dict[str, Any], expr.value)
    lst = cast(list[Any], value["v"])
    with pytest.raises(TypeError):
        lst *= 2  # type: ignore[assignment]
    assert lst == [1], "__imul__ no debe mutar la lista antes del rebind"
    with pytest.raises(TypeError):
        lst += [2]  # type: ignore[assignment]
    assert lst == [1]

    assert copy(expr) == expr
    deep = deepcopy(expr)
    assert deep == expr
    deep_value = cast(dict[str, Any], deep.value)
    with pytest.raises(TypeError):
        cast(list[Any], deep_value["v"]).append(9)  # deepcopy conserva inmutabilidad


def test_model_copy_revalida_y_congela() -> None:
    expr = GuardExpr(op="eq", path=("world", "x"), value={"v": [1]})
    with pytest.raises(ValidationError):
        expr.model_copy(update={"op": "execute"})
    with pytest.raises(ValidationError):
        expr.model_copy(update={"path": ()})
    nuevo = expr.model_copy(update={"value": {"v": [2]}})
    assert cast(dict[str, Any], nuevo.value) == {"v": [2]}
    with pytest.raises(TypeError):
        cast(list[Any], cast(dict[str, Any], nuevo.value)["v"]).append(3)


def test_variables_y_model_copy_congelados() -> None:
    inst = _instance()
    with pytest.raises(TypeError):
        cast(dict[str, Any], inst.variables)["x"] = 1
    nuevo = inst.with_state("closed", 1, {"deadline": "2026-10-06"}, datetime.now())
    with pytest.raises(TypeError):
        cast(dict[str, Any], nuevo.variables)["deadline"] = "2026-10-07"
    assert nuevo.state == "closed"
    assert nuevo.revision == 1


def test_value_binding_literal_null() -> None:
    assert ValueBinding(literal=None).is_literal
    assert not ValueBinding(snapshot_path=("machines", "x", "state")).is_literal
    with pytest.raises(ValidationError):
        ValueBinding()
    with pytest.raises(ValidationError):
        ValueBinding(literal=1, snapshot_path=("a",))


def test_decision_y_comando_estables() -> None:
    decision = TransitionDecision(
        instance_ref=MI1,
        event_id="ev-1",
        expected_revision=0,
        previous_state="open",
        next_state="closed",
        transition_ref="t-1",
        snapshot_hash="sh",
    )
    command = MachineCommand(
        id="c-1",
        kind="event",
        target_ref=MI1,
        payload={"x": 1},
        scope=Scope(client_id="c1"),
        correlation_id="corr",
    )
    assert decision.commands == ()
    assert command.kind == "event"


def test_hash_helpers_estables() -> None:
    def make(content_hash: str) -> MachineDefinition:
        return MachineDefinition(
            ref=DEF, version="1", content_hash=content_hash, family="f",
            initial_state="open", states=(StateDefinition(id="open"),),
            transitions=(), event_schemas={"e": {"type": "object"}},
            variables_schema={"type": "object"},
        )

    a = make("x")
    b = a.model_copy(update={"content_hash": "y"})
    assert machine_definition_hash(a) == machine_definition_hash(b)
    assert machine_definition_hash(a) != machine_definition_hash(make("x").model_copy(update={"family": "g"}))
    payload = machine_definition_payload(a)
    assert payload["ref"] == "kb:Machine:m1@rel-1"
    assert payload["states"] == [{"id": "open", "terminal": False}]


def test_machine_graph_neutral() -> None:
    from cognitive import EventTypeGraphDoc, GraphCompiler, StateGraphDoc

    graph = MachineGraph(
        machine=MachineGraphDoc(
            id="machine:m1", title="Consent", version="1", family="consent",
            initial_state_ref=DEF, state_refs=(DEF,), transition_refs=(),
            event_type_refs=(DEF,),
        ),
        states=(
            StateGraphDoc(id="s:open", machine_ref=DEF),
            StateGraphDoc(id="s:closed", machine_ref=DEF, terminal=True),
        ),
        events=(EventTypeGraphDoc(id="evt:close", machine_ref=DEF, name="close"),),
    )
    assert len(graph.states) == 2
    assert isinstance(GraphCompiler, type)  # Protocol accesible
    assert isinstance(graph.machine, MachineGraphDoc)
    assert graph.edges_of("has_state") == ()


def test_context_snapshot_frozen() -> None:
    ctx = ContextSnapshot(
        self_assignment_ref=Ref.parse("self_assignment:sa-1"),
        execution_scope_ref=Ref.parse("conversation:c-1"),
        scope=Scope(client_id="c1"),
    )
    assert ctx.projection_hash == ""
    with pytest.raises(ValidationError):
        ctx.allowed_action_refs = (DEF,)  # type: ignore[misc]


def test_event_scope_preservado() -> None:
    event = Event(
        id="ev-1",
        type="closed",
        scope=Scope(client_id="c1", subject_ref=Ref.parse("subject:s-1")),
        owner_ref=Ref.parse("subject:s-1"),
        source_ref=Ref.parse("conversation:c-1"),
        occurred_at=T0,
        correlation_id="corr",
    )
    assert event.scope.subject_ref == Ref.parse("subject:s-1")


def test_tiempos_utc_normalizados() -> None:

    naive = Event(
        id="hit:1", type="t", scope=Scope(client_id="c1"),
        owner_ref=Ref.parse("subject:s-1"), source_ref=Ref.parse("conversation:c-1"),
        occurred_at=datetime(2026, 10, 5, 12, 0, 0), correlation_id="corr",
    )
    assert naive.occurred_at.utcoffset() == UTC.utcoffset(None)  # type: ignore[union-attr]
    assert naive.occurred_at.hour == 12  # naive se interpreta como UTC, sin salto
    offset = Event(
        id="hit:2", type="t", scope=Scope(client_id="c1"),
        owner_ref=Ref.parse("subject:s-1"), source_ref=Ref.parse("conversation:c-1"),
        occurred_at=cast(datetime, "2026-10-05T14:30:00+02:00"), correlation_id="corr",
    )
    assert offset.occurred_at.hour == 12
    z = Event(
        id="hit:3", type="t", scope=Scope(client_id="c1"),
        owner_ref=Ref.parse("subject:s-1"), source_ref=Ref.parse("conversation:c-1"),
        occurred_at=cast(datetime, "2026-10-05T00:00:00Z"), correlation_id="corr",
    )
    assert z.occurred_at.tzinfo is not None


def test_external_receipt_enum_y_revision() -> None:
    from cognitive import ExternalReceipt, invocation_fingerprint

    for status in ("pending", "accepted", "confirmed", "rejected", "unknown"):
        receipt = ExternalReceipt(
            ref=Ref.parse("receipt:r-1"), invocation_id="inv-1", operation="sms.send",
            status=status, observed_at=datetime(2026, 10, 5), revision="rev-1",
            scope=Scope(client_id="c1"),
        )
        assert receipt.revision == "rev-1"
    with pytest.raises(ValidationError):
        ExternalReceipt(
            ref=Ref.parse("receipt:r-1"), invocation_id="inv-1", operation="sms.send",
            status=cast(Any, "succeeded"), observed_at=datetime(2026, 10, 5), revision="rev-1",
            scope=Scope(client_id="c1"),
        )  # never conflate with ActionResult.status

    f1 = invocation_fingerprint("sms.send", {"to": "x", "body": "a"})
    f2 = invocation_fingerprint("sms.send", {"body": "a", "to": "x"})
    f3 = invocation_fingerprint("sms.send", {"to": "x", "body": "b"})
    assert f1 == f2  # JSON ordenado: mismo objeto, misma huella
    assert f1 != f3


def test_receipt_reservation_dto() -> None:
    from cognitive import ReceiptReservation

    reservation = ReceiptReservation(
        ref=Ref.parse("receipt:r-1"), invocation_id="inv-1", operation="sms.send",
        owner_ref=Ref.parse("subject:s-1"), scope=Scope(client_id="c1"),
        input_fingerprint="abc123", status="reserved", revision="rev-0",
    )
    assert reservation.input_fingerprint == "abc123"
    with pytest.raises(ValidationError):
        reservation.model_copy(update={"status": "delivered"})


class _NestedTuples(FrozenModel):
    """DTO de prueba: tupla de tuplas con dicts anidados (regresión _freeze)."""

    value: tuple[tuple[dict[str, JsonValue], ...], ...]


class _TwoMaps(FrozenModel):
    """DTO de prueba: dos campos que reciben el MISMO dict de entrada."""

    a: dict[str, JsonValue]
    b: dict[str, JsonValue]


def test_deepcopy_decision_con_comandos_y_payload() -> None:
    """Shape reportada por SQL worker (w10:p15): comandos con payload dict real."""
    scope = Scope(client_id="c1", subject_ref=Ref.parse("subject:s-1"))
    command = MachineCommand(
        id="cmd-1", kind="action", target_ref=Ref.parse("tool:send"),
        payload={"monto": 7, "tags": ["a", 1, None]},
        scope=scope, correlation_id="corr-1", causation_id=None,
    )
    decision = TransitionDecision(
        instance_ref=MI1, event_id="ev-1", expected_revision=0,
        previous_state="open", next_state="closed", transition_ref="t-1",
        snapshot_hash="sh", commands=(command,),
    )
    payload = cast(dict[str, Any], decision.commands[0].payload)
    with pytest.raises(TypeError):
        cast(list[Any], payload["tags"]).append("x")  # payload congelado

    for copied in (deepcopy(decision), decision.model_copy(), decision.model_copy(deep=True)):
        assert copied.commands[0].payload == {"monto": 7, "tags": ["a", 1, None]}
        with pytest.raises(TypeError):
            cast(list[Any], cast(dict[str, Any], copied.commands[0].payload)["tags"]).append("y")

    decision2 = decision.model_copy(
        update={"commands": (command.model_copy(update={"payload": {"z": [1]}}),)}
    )
    assert decision2.commands[0].payload == {"z": [1]}


def test_tuple_anidada_con_dicts_congelada() -> None:
    outer = _NestedTuples(value=(({"a": [1]},),))
    inner = outer.value[0][0]["a"]
    lst = cast(list[Any], inner)
    with pytest.raises(TypeError):
        lst.append(2)  # dict dentro de tupla dentro de tupla queda congelado
    assert lst == [1]

    clone = deepcopy(outer)
    with pytest.raises(TypeError):
        cast(list[Any], clone.value[0][0]["a"]).append(3)


def test_clonados_no_aliasan_contenedores() -> None:
    shared: dict[str, JsonValue] = {"k": [1]}
    m = _TwoMaps(a=shared, b=shared)
    # entrada compartida => contenedores congelados DISTINTOS (copia defensiva por campo)
    assert m.a is not m.b
    for field in ("a", "b"):
        with pytest.raises(TypeError):
            cast(list[Any], cast(dict[str, Any], getattr(m, field))["k"]).append(2)

    for clone in (copy(m), deepcopy(m), m.model_copy(), m.model_copy(deep=True)):
        assert clone.a == clone.b == {"k": [1]}
        with pytest.raises(TypeError):
            cast(list[Any], cast(dict[str, Any], clone.a)["k"]).append(3)
        with pytest.raises(TypeError):
            cast(list[Any], cast(dict[str, Any], clone.b)["k"]).append(3)


def test_utc_none_reporta_validation_error() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="occurred_at"):
        Event(
            id="e-1", type="t", scope=Scope(client_id="c1"),
            owner_ref=MI1, source_ref=MI1, occurred_at=cast(Any, None),
            correlation_id="c-1", causation_id=None,
        )


def test_machine_graph_doc_campos_autorales() -> None:
    from cognitive import TransitionGraphDoc

    graph = MachineGraphDoc(
        id="m1", title="M", version="1", family="f",
        initial_state_ref=DEF,
        variables_schema={"type": "object", "properties": {"v": {"type": "integer"}}},
    )
    assert graph.variables_schema == {"type": "object", "properties": {"v": {"type": "integer"}}}
    assert MachineGraphDoc(
        id="m2", title="M2", version="1", family="f",
        initial_state_ref=DEF,
    ).variables_schema is None  # ausencia autoral preservada, no forzada a {}

    transition = TransitionGraphDoc(
        id="t-1", machine_ref=MI1, source_ref=DEF,
        target_ref=DEF, event_type_ref=DEF,
        assignments={"sent": ValueBinding(literal=True),
                     "obs": ValueBinding(snapshot_path=("world", "observation:o1", "id"))},
    )
    assert transition.assignments == {
        "sent": ValueBinding(literal=True),
        "obs": ValueBinding(snapshot_path=("world", "observation:o1", "id")),
    }
    assert TransitionGraphDoc(
        id="t-2", machine_ref=MI1, source_ref=DEF,
        target_ref=DEF, event_type_ref=DEF,
    ).assignments == {}


def test_freeze_json_snapshot_publico() -> None:
    from cognitive import freeze_json_snapshot

    raw: dict[str, JsonValue] = {
        "world": {"observation:o1": {"value": {"monto": [1, 2]}}},
        "machines": {"machine_instance:m-1": {"state": "open"}},
    }
    snap = freeze_json_snapshot(raw)
    world = snap["world"]
    nested = cast(dict[str, Any], cast(dict[str, Any], world)["observation:o1"])
    with pytest.raises(TypeError):
        cast(list[Any], nested["value"]["monto"]).append(3)  # tipo: ignore[union-attr]
    # las claves deben poder indexarse por str(ref) (proyección/context)
    assert "machine_instance:m-1" in snap["machines"]

    # idempotente: ya congelado => misma instancia
    again = freeze_json_snapshot(snap)
    assert again is snap
