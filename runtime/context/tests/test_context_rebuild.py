"""Projection rebuild uses durable SQL bytes and excludes unselected observations."""

from pathlib import Path

import pytest

from cognitive import Observation, Scope
from data.world_evidence import EvidenceSelectionError
from ontology import Ref
from runtime.context.tests.projection_support import NOW, PROCESS, SCOPE, SELF, Substrate


def test_rebuild_mismo_hash_y_contenido(tmp_path: Path) -> None:
    substrate = Substrate(tmp_path)
    first = substrate.projector().project(SELF, PROCESS, SCOPE)
    from data import SqlStore
    from data.machines import (
        SqlActionExecutionStore,
        SqlGoalStore,
        SqlKnowledgeStore,
        SqlMachineRepository,
        SqlProcessStore,
        SqlSelfAssignmentStore,
    )
    from data.world_evidence import SqlEvidenceSelection, SqlWorldEvidenceRepository

    # Reopen durable repositories with a separate database engine and no cached snapshot.
    reopened = SqlStore(f"sqlite:///{tmp_path / 'runtime.db'}")
    substrate.machines = SqlMachineRepository(reopened, substrate.privacy)
    substrate.assignments = SqlSelfAssignmentStore(reopened, substrate.privacy)
    substrate.processes = SqlProcessStore(reopened, substrate.privacy)
    substrate.goals = SqlGoalStore(reopened, substrate.privacy)
    substrate.knowledge = SqlKnowledgeStore(reopened, substrate.privacy)
    substrate.executions = SqlActionExecutionStore(reopened, substrate.privacy)
    substrate.evidence = SqlWorldEvidenceRepository(reopened, substrate.privacy)
    substrate.selection = SqlEvidenceSelection(reopened, clock=lambda: NOW)
    second = substrate.projector().project(SELF, PROCESS, SCOPE)
    assert first == second
    assert first.projection_hash == second.projection_hash


def test_dato_no_observado_queda_fuera(tmp_path: Path) -> None:
    substrate = Substrate(tmp_path)
    substrate.evidence.put_observation(
        Observation(
            ref=Ref.parse("observation:hidden"),
            source_ref=Ref.parse("tool:source"),
            observed_at=NOW,
            revision="r2",
            value={"secret": True},
            scope=SCOPE,
        )
    )
    snapshot = substrate.projector().project(SELF, PROCESS, SCOPE)
    assert [o["ref"] for o in snapshot.observations] == ["observation:o1"]


def test_fail_closed_si_evidencia_citada_falta(tmp_path: Path) -> None:
    substrate = Substrate(tmp_path)
    substrate.remove_observation()
    with pytest.raises(EvidenceSelectionError):
        substrate.projector().project(SELF, PROCESS, SCOPE)


@pytest.mark.parametrize(
    "scope", [Scope(client_id="other"), Scope(client_id="projection", subject_ref=Ref.parse("subject:other"))]
)
def test_privacy_sql(tmp_path: Path, scope: Scope) -> None:
    substrate = Substrate(tmp_path)
    with pytest.raises(PermissionError):
        substrate.projector().project(SELF, PROCESS, scope)
