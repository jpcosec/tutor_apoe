"""Immutable snapshots and authorized production SQL projection."""

from collections.abc import MutableMapping
from pathlib import Path
from typing import cast

import pytest

from cognitive.jsons import JsonValue
from context.substrates import EvidenceError, SnapshotBuilder
from data.world_evidence import EvidenceSelectionError
from ontology import Ref
from runtime.context.tests.projection_support import (
    MACHINE,
    NOW,
    OBSERVATION,
    PROCESS,
    SCOPE,
    SELF,
    Substrate,
)


def test_snapshot_freeze_profundo() -> None:
    original: dict[str, JsonValue] = {"k": {"nested": [1, 2, {"deep": True}]}}
    snapshot = SnapshotBuilder().build(observations=original, machines={}, actor={}, event={})
    mutable = cast(MutableMapping[str, JsonValue], snapshot)
    with pytest.raises(TypeError):
        mutable.update({"x": 1})
    with pytest.raises(TypeError):
        mutable.clear()
    with pytest.raises(TypeError):
        mutable.pop("world")
    with pytest.raises(TypeError):
        mutable.setdefault("x", 1)
    with pytest.raises(TypeError):
        cast(dict[str, JsonValue], mutable).__ior__({"x": 1})
    world = cast(dict[str, JsonValue], snapshot["world"])
    nested = cast(dict[str, JsonValue], world["k"])
    values = cast(list[JsonValue], nested["nested"])
    with pytest.raises(TypeError):
        values.append(3)
    with pytest.raises(TypeError):
        cast(dict[str, JsonValue], values[2])["deep"] = False
    original_values = cast(list[JsonValue], cast(dict[str, JsonValue], original["k"])["nested"])
    original_values.append(99)
    cast(dict[str, JsonValue], original_values[2])["deep"] = False
    original.clear()
    assert values[1] == 2
    assert len(values) == 3
    assert cast(dict[str, JsonValue], values[2])["deep"] is True


def test_snapshot_claves_exactas() -> None:
    snapshot = SnapshotBuilder().build(
        observations={str(OBSERVATION): {"value": 1}},
        machines={str(MACHINE): {"state": "active"}},
        actor={},
        event={},
    )
    assert set(snapshot) == {"world", "machines", "actor", "event"}
    assert str(OBSERVATION) in cast(dict[str, JsonValue], snapshot["world"])
    assert str(MACHINE) in cast(dict[str, JsonValue], snapshot["machines"])


def test_projection_incluye_revision_y_reasons(tmp_path: Path) -> None:
    substrate = Substrate(tmp_path)
    snapshot = substrate.projector().project(SELF, PROCESS, SCOPE)
    assert snapshot.machine_snapshots[0]["ref"] == str(MACHINE)
    assert snapshot.observations[0]["revision"] == "opaque-r1"
    assert snapshot.observations[0]["observed_at"] == NOW.isoformat()
    assert snapshot.allowed_action_refs == (Ref.parse("kb:ActionDoc:a1@r1"),)
    assert snapshot.goal_status == {"goal_instance:g1": "active"}
    assert str(OBSERVATION) in snapshot.inclusion_reasons


def test_fail_closed_sin_evidencia_citada(tmp_path: Path) -> None:
    substrate = Substrate(tmp_path)
    substrate.remove_observation()
    with pytest.raises(EvidenceSelectionError):
        substrate.projector().project(SELF, PROCESS, SCOPE)


def test_context_no_transiciona_machine(tmp_path: Path) -> None:
    substrate = Substrate(tmp_path)
    before = substrate.machines.load(MACHINE, SCOPE)
    substrate.projector().project(SELF, PROCESS, SCOPE)
    assert substrate.machines.load(MACHINE, SCOPE) == before


def test_stale_required_revision_rejected(tmp_path: Path) -> None:
    substrate = Substrate(tmp_path)
    observation = substrate.evidence.get_observation(OBSERVATION, SCOPE)
    assert observation is not None
    substrate.evidence.put_observation(observation.model_copy(update={"revision": "newer-r2"}))
    with pytest.raises(EvidenceSelectionError, match="stale revision"):
        substrate.projector().project(SELF, PROCESS, SCOPE)


def test_expired_persisted_observation_rejected(tmp_path: Path) -> None:
    substrate = Substrate(tmp_path)
    observation = substrate.evidence.get_observation(OBSERVATION, SCOPE)
    assert observation is not None
    substrate.evidence.put_observation(observation.model_copy(update={"expires_at": NOW}))
    with pytest.raises(EvidenceSelectionError, match="expired"):
        substrate.projector().project(SELF, PROCESS, SCOPE)


def test_actor_cannot_choose_unrelated_process(tmp_path: Path) -> None:
    substrate = Substrate(tmp_path)
    process = substrate.processes.load(PROCESS, SCOPE)
    assert process is not None
    substrate.processes.update(process.model_copy(update={"participant_refs": ()}))
    with pytest.raises(PermissionError, match="no participa"):
        substrate.projector().project(SELF, PROCESS, SCOPE)


def test_execution_scope_requires_persisted_parent_port(tmp_path: Path) -> None:
    substrate = Substrate(tmp_path)
    with pytest.raises(EvidenceError, match="no authorized process"):
        substrate.projector().project(SELF, Ref.parse("action_execution:x1"), SCOPE)


def test_execution_parent_loaded_from_sql(tmp_path: Path) -> None:
    from cognitive import ActionInvocation

    substrate = Substrate(tmp_path)
    execution = Ref.parse("action_execution:x1")
    substrate.executions.reserve(
        ActionInvocation(
            ref=execution,
            action_ref=Ref.parse("kb:ActionDoc:a1@r1"),
            action_hash="ah",
            release_id="r1",
            owner_ref=PROCESS,
            actor_assignment_ref=SELF,
            inputs={},
            scope=SCOPE,
            idempotency_key="parent-test",
            process_ref=PROCESS,
        )
    )
    snapshot = substrate.projector().project(SELF, execution, SCOPE)
    assert snapshot.execution_scope_ref == execution
    assert str(PROCESS) in snapshot.inclusion_reasons


def test_required_goal_evidence_needs_durable_pin(tmp_path: Path) -> None:
    from cognitive import Observation

    substrate = Substrate(tmp_path)
    required = Ref.parse("observation:required")
    substrate.evidence.put_observation(
        Observation(
            ref=required,
            source_ref=Ref.parse("tool:source"),
            observed_at=NOW,
            revision="required-r1",
            value={"amount": 10},
            scope=SCOPE,
        )
    )
    goal = substrate.goals.load(Ref.parse("goal_instance:g1"), SCOPE)
    assert goal is not None
    substrate.goals.update(goal.model_copy(update={"evidence_refs": (required,)}))
    with pytest.raises(EvidenceError, match="pinned revision"):
        substrate.projector().project(SELF, PROCESS, SCOPE)
    substrate.selection.bind(PROCESS, required, SCOPE, revision="required-r1")
    snapshot = substrate.projector().project(SELF, PROCESS, SCOPE)
    assert {str(o["ref"]) for o in snapshot.observations} == {str(OBSERVATION), str(required)}
