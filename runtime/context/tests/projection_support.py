"""Production SQL substrate used by canonical projection tests."""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete

from cognitive import GoalInstance, MachineInstance, Observation, ProcessInstance, Scope, SelfAssignment
from context.knowledge import KnowledgeLifecycle
from context.substrates import ContextProjector, SelfDeclarations
from data import Privacy, SqlStore
from data.machines import (
    SqlActionExecutionStore,
    SqlGoalStore,
    SqlKnowledgeStore,
    SqlMachineRepository,
    SqlProcessStore,
    SqlSelfAssignmentStore,
)
from data.privacy import Scrubber
from data.vault import Vault
from data.world_evidence import SqlEvidenceSelection, SqlWorldEvidenceRepository, WorldObservationRow
from ontology import Ref

NOW = datetime(2026, 10, 5, tzinfo=UTC)
SCOPE = Scope(client_id="projection", subject_ref=Ref.parse("subject:s1"))
SELF = Ref.parse("self_assignment:s1")
PROCESS = Ref.parse("process_instance:p1")
MACHINE = Ref.parse("machine_instance:m1")
OBSERVATION = Ref.parse("observation:o1")


class Declarations:
    def action_hash(self, action_ref: Ref, scope: Scope) -> str:
        return "authored-action-hash"

    def declared_actions(self, self_ref: Ref, scope: Scope) -> tuple[Ref, ...]:
        return (Ref.parse("kb:ActionDoc:a1@r1"), Ref.parse("kb:ActionDoc:a2@r1"))


class Substrate:
    def __init__(self, root: Path) -> None:
        self.store = SqlStore(f"sqlite:///{root / 'runtime.db'}")
        self.privacy = Privacy(Scrubber(), Vault(f"sqlite:///{root / 'vault.db'}"))
        self.machines = SqlMachineRepository(self.store, self.privacy)
        self.assignments = SqlSelfAssignmentStore(self.store, self.privacy)
        self.processes = SqlProcessStore(self.store, self.privacy)
        self.goals = SqlGoalStore(self.store, self.privacy)
        self.evidence = SqlWorldEvidenceRepository(self.store, self.privacy)
        self.knowledge = SqlKnowledgeStore(self.store, self.privacy)
        self.executions = SqlActionExecutionStore(self.store, self.privacy)
        self.selection = SqlEvidenceSelection(self.store, clock=lambda: NOW)
        self.machines.create(
            MachineInstance(
                ref=MACHINE,
                definition_ref=Ref.parse("kb:MachineDoc:m1@r1"),
                definition_hash="mh",
                release_id="r1",
                owner_ref=SCOPE.subject_ref or PROCESS,
                scope=SCOPE,
                state="active",
                revision=0,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        self.assignments.create(
            SelfAssignment(
                ref=SELF,
                self_definition_ref=Ref.parse("kb:SelfDoc:s1@r1"),
                self_definition_hash="sh",
                actor_ref=Ref.parse("actor:a1"),
                scope=SCOPE,
                granted_capabilities=frozenset({"action:a1"}),
                machine_ref=MACHINE,
            )
        )
        goal = Ref.parse("goal_instance:g1")
        self.goals.create(
            GoalInstance(
                ref=goal,
                goal_definition_ref=Ref.parse("kb:GoalDoc:g1@r1"),
                goal_definition_hash="gh",
                owner_ref=PROCESS,
                scope=SCOPE,
                machine_ref=MACHINE,
                status="inactive",
            )
        )
        self.processes.create(
            ProcessInstance(
                ref=PROCESS,
                process_definition_ref=Ref.parse("kb:ProcessDoc:p1@r1"),
                process_definition_hash="ph",
                scope=SCOPE,
                machine_refs=(MACHINE,),
                goal_refs=(goal,),
                participant_refs=(SELF,),
            )
        )
        self.evidence.put_observation(
            Observation(
                ref=OBSERVATION,
                value={"amount": 42},
                source_ref=Ref.parse("tool:source"),
                observed_at=NOW,
                revision="opaque-r1",
                scope=SCOPE,
            )
        )

        self.selection.bind(PROCESS, OBSERVATION, SCOPE, revision="opaque-r1")

    def remove_observation(self) -> None:
        with self.store.writing() as session:
            session.execute(
                delete(WorldObservationRow).where(
                    WorldObservationRow.client_id == SCOPE.client_id,
                    WorldObservationRow.ref == str(OBSERVATION),
                )
            )

    def projector(self, declarations: SelfDeclarations | None = None) -> ContextProjector:
        return ContextProjector(
            machine_repo=self.machines,
            self_assignments=self.assignments,
            processes=self.processes,
            goals=self.goals,
            world_evidence=self.evidence,
            evidence_selection=self.selection,
            self_declarations=declarations or Declarations(),
            knowledge=KnowledgeLifecycle(self.knowledge, now=lambda: NOW),
            now=lambda: NOW,
            execution_processes=self.executions,
        )
