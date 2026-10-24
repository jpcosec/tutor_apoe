"""Sustratos de proyección: snapshot puro y proyección de contexto (api-canonica §13).

Implementa el `SnapshotBuilder` puro (claves exactas ``world[str(Observation.ref)]`` y
``machines[str(MachineInstance.ref)]``, inmutable profundo) y el `ContextProjector` que arma
un `ContextSnapshot` autorizado desde stores neutrales inyectados.

Principios:
- Context lee estado de máquina pero jamás lo transiciona.
- La evidencia NO se lee a través del World de negocio: se inyecta un selector de evidencia
  (`EvidenceSelection`) que devuelve los refs de Observaciones persistidas citadas por la
  ejecución, y cada una se carga por `WorldEvidenceRepository.get_observation`.
- Evidencia faltante u obsoleta (expiry) ⇒ fail-closed (no proyecto incompleto).
- `allowed_action_refs` = Self.can_perform declarado ∩ grants efectivos del SelfAssignment.
- Origen: compile el hash canónico determinista (reconstruible sin cache).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Protocol, cast, runtime_checkable

from cognitive import (
    ContextSnapshot,
    GoalInstance,
    GoalStore,
    MachineInstance,
    MachineRepository,
    Observation,
    ProcessInstance,
    ProcessStore,
    Scope,
    SelfAssignment,
    SelfAssignmentStore,
    Snapshot,
    WorldEvidenceRepository,
    freeze_json_snapshot,
)
from cognitive import (
    SnapshotBuilder as _SnapshotBuilderProto,
)
from cognitive.jsons import JsonValue
from context.knowledge import KnowledgeLifecycle
from kb import KnowledgeBase, SldbDeclarations
from ontology import Ref


def _canonical(blob: object) -> str:
    return hashlib.sha256(
        json.dumps(blob, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode(
            "utf-8"
        )
    ).hexdigest()


class SnapshotBuilder(_SnapshotBuilderProto):
    """Constructor puro del snapshot {world, machines, actor, event} para evaluación.

    Claves exactas: `world[str(Observation.ref)]` y `machines[str(MachineInstance.ref)]`.
    Inmutable profundo (core `freeze_json_snapshot`): la raíz Y los dict/list anidados
    rechazan `=`, `update`, `clear`, `pop`, `setdefault`, `|=`, `append`, etc.
    Sin I/O: entrada estable para guards y criterios de Goal.
    """

    def build(
        self,
        *,
        observations: Mapping[str, JsonValue],
        machines: Mapping[str, JsonValue],
        actor: Mapping[str, JsonValue],
        event: Mapping[str, JsonValue],
    ) -> Snapshot:
        raw = {
            "world": dict(observations),
            "machines": dict(machines),
            "actor": dict(actor),
            "event": dict(event),
        }
        return cast(Snapshot, freeze_json_snapshot(raw))


@runtime_checkable
class EvidenceSelection(Protocol):
    """Port neutral: refs de Observaciones persistidas citadas por una ejecución.

    Lo implementa el worker de World/persistencia; nunca expone máquinas ni procesos.
    """

    def observations_for(self, execution_scope: Ref, scope: Scope) -> tuple[Ref, ...]: ...

    def revision_for(self, execution_scope: Ref, observation_ref: Ref, scope: Scope) -> str | None: ...


@runtime_checkable
class SelfDeclarations(Protocol):
    """Port neutral: refs de actions que el Self declara poder realizar (Self.can_perform)."""

    def declared_actions(self, self_ref: Ref, scope: Scope) -> tuple[Ref, ...]: ...

    def action_hash(self, action_ref: Ref, scope: Scope) -> str: ...


class KbSelfDeclarations:
    """SelfDeclarations desde el GRAFO REAL de la KB: aristas `can_perform` (SelfDoc→ActionDoc).

    Lee `KnowledgeBase.outgoing(self_ref_id, "can_perform")`, no solo los refs del payload:
    la KB valida `can_perform` contra aristas reales, así que la declaración efectiva
    coincide con el grafo (no con textura de payload).
    """

    def __init__(self, kb: KnowledgeBase, *, declarations: SldbDeclarations | None = None) -> None:
        self._kb = kb
        self._declarations = declarations or SldbDeclarations(kb)
        if self._declarations.fingerprint() != kb.fingerprint:
            raise ValueError("Self declarations and relation graph have different source fingerprints")

    def declared_actions(self, self_ref: Ref, scope: Scope) -> tuple[Ref, ...]:
        refs: list[Ref] = []
        key = self_ref.id
        self._declarations.resolve(self_ref)
        relations = self._kb.outgoing(key, "can_perform")
        for relation in relations:
            refs.append(Ref(kind="kb", id=relation.target_ref, release_id=self_ref.release_id))
        return tuple(dict.fromkeys(refs))

    def action_hash(self, action_ref: Ref, scope: Scope) -> str:
        document = self._declarations.resolve(action_ref)
        if not document.is_a("ActionDoc") or not document.content_hash:
            raise EvidenceError(f"missing authored action provenance: {action_ref}")
        return document.content_hash


class ExecutionProcesses(Protocol):
    """Persisted execution-to-process relation; supplied by the SQL owner."""

    def lookup_process(self, execution_ref: Ref, scope: Scope) -> Ref | None: ...


class ContextProjector:
    """Dueño del snapshot autorizado para un SelfAssignment + execution_scope.

    Depende de stores neutrales inyectados; no guarda estado autoritativo propio.
    Fail-closed: rol no autorizado o evidencia faltante/obsoleta ⇒ error.
    Context jamás transiciona una máquina.
    """

    def __init__(
        self,
        *,
        machine_repo: MachineRepository,
        self_assignments: SelfAssignmentStore,
        processes: ProcessStore,
        goals: GoalStore,
        world_evidence: WorldEvidenceRepository,
        evidence_selection: EvidenceSelection,
        self_declarations: SelfDeclarations,
        knowledge: KnowledgeLifecycle,
        now: Callable[[], datetime],
        builder: _SnapshotBuilderProto | None = None,
        execution_processes: ExecutionProcesses | None = None,
    ) -> None:
        self._machine = machine_repo
        self._self_assignments = self_assignments
        self._processes = processes
        self._goals = goals
        self._world_evidence = world_evidence
        self._evidence_selection = evidence_selection
        self._self_declarations = self_declarations
        self._knowledge = knowledge
        self._now = now
        self._builder = builder or SnapshotBuilder()
        self._execution_processes = execution_processes

    def project(self, self_assignment: Ref, execution_scope: Ref, scope: Scope) -> ContextSnapshot:
        assignment = self._load_self(self_assignment, scope)
        process = self._load_process(execution_scope, scope, assignment)

        machine_snapshots: list[dict[str, JsonValue]] = []
        definition_refs: list[Ref] = []
        definition_hashes: dict[str, str] = {}
        instances: list[MachineInstance] = []
        for machine_ref in self._machine_refs(assignment, process):
            instance = self._load_machine(machine_ref, scope)
            instances.append(instance)
            machine_snapshots.append(self._machine_record(instance))
            definition_refs.append(instance.definition_ref)
            definition_hashes[str(instance.definition_ref)] = instance.definition_hash

        goals = self._goals_for(process, scope)
        for goal in goals:
            if goal.machine_ref not in {i.ref for i in instances}:
                instance = self._load_machine(goal.machine_ref, scope)
                instances.append(instance)
                machine_snapshots.append(self._machine_record(instance))
                definition_refs.append(instance.definition_ref)
                definition_hashes[str(instance.definition_ref)] = instance.definition_hash
        states = {instance.ref: instance.state for instance in instances}
        goal_status = {str(goal.ref): states[goal.machine_ref] for goal in goals}
        expected_definitions = [
            (assignment.self_definition_ref, assignment.self_definition_hash),
            (process.process_definition_ref, process.process_definition_hash),
        ]
        expected_definitions.extend((goal.goal_definition_ref, goal.goal_definition_hash) for goal in goals)
        expected_definitions.extend(
            (instance.definition_ref, instance.definition_hash) for instance in instances
        )
        for definition_ref, content_hash in expected_definitions:
            key = str(definition_ref)
            previous = definition_hashes.get(key)
            if previous is not None and previous != content_hash:
                raise EvidenceError(f"inconsistent pinned definition hash: {definition_ref}")
            definition_refs.append(definition_ref)
            definition_hashes[key] = content_hash
        required = tuple(ref for goal in goals for ref in goal.evidence_refs)
        observations = self._authorized_evidence(execution_scope, scope, required)
        allowed_actions = self._allowed_actions(assignment, scope)
        knowledge_versions, activation_refs = self._knowledge_for(assignment, execution_scope, scope)

        inclusion = dict(self._inclusion_reasons(instances, goals, observations, knowledge_versions))
        inclusion[str(assignment.ref)] = (
            f"source={assignment.self_definition_ref}",
            f"hash={assignment.self_definition_hash}",
            f"revision={assignment.revision}",
        )
        inclusion[str(process.ref)] = (
            f"source={process.process_definition_ref}",
            f"hash={process.process_definition_hash}",
            f"revision={process.revision}",
        )
        for action_ref in allowed_actions:
            action_hash = self._self_declarations.action_hash(action_ref, scope)
            if not action_hash:
                raise EvidenceError(f"missing action hash: {action_ref}")
            inclusion[str(action_ref)] = (
                "self-can_perform-and-server-grant",
                f"source={action_ref}",
                f"hash={action_hash}",
                f"grant=action:{action_ref.id.rsplit(':', 1)[-1]}",
            )
        for activation_ref in activation_refs:
            activation = self._knowledge.load_activation(activation_ref, scope)
            if activation is None or activation.status != "active":
                raise EvidenceError(f"activation changed during projection: {activation_ref}")
            inclusion[str(activation_ref)] = (
                "consumer-activation",
                f"revision={activation.revision}",
                f"source={activation.knowledge_version_ref}",
                f"consumer={activation.self_assignment_ref}",
                f"execution_scope={activation.execution_scope_ref}",
            )
        for version_ref in knowledge_versions:
            version = self._knowledge.load_version(version_ref, scope)
            if version is None or not version.eligible:
                raise EvidenceError(f"knowledge version changed during projection: {version_ref}")
            inclusion[str(version_ref)] = (
                "knowledge-publicado-activo",
                f"source={version.knowledge_definition_ref}",
                f"hash={version.content_hash}",
                f"version={version.version}",
                f"release={version.release_id}",
            )
        snapshot = ContextSnapshot(
            self_assignment_ref=assignment.ref,
            execution_scope_ref=execution_scope,
            scope=scope,
            definition_refs=tuple(dict.fromkeys(definition_refs)),
            definition_hashes=definition_hashes,
            machine_snapshots=tuple(machine_snapshots),
            observations=tuple(self._observation_record(o) for o in observations),
            goal_refs=tuple(g.ref for g in goals),
            goal_status=goal_status,
            allowed_action_refs=allowed_actions,
            knowledge_versions=tuple(dict.fromkeys(knowledge_versions)),
            activation_refs=tuple(dict.fromkeys(activation_refs)),
            inclusion_reasons=inclusion,
        )
        verification = {
            "self_assignment_ref": str(snapshot.self_assignment_ref),
            "execution_scope_ref": str(snapshot.execution_scope_ref),
            "scope": json.loads(snapshot.scope.model_dump_json()),
            "definition_refs": [str(r) for r in snapshot.definition_refs],
            "definition_hashes": snapshot.definition_hashes,
            "machine_snapshots": snapshot.machine_snapshots,
            "observations": snapshot.observations,
            "goal_refs": [str(r) for r in snapshot.goal_refs],
            "goal_status": snapshot.goal_status,
            "allowed_action_refs": [str(r) for r in snapshot.allowed_action_refs],
            "knowledge_versions": [str(r) for r in snapshot.knowledge_versions],
            "activation_refs": [str(r) for r in snapshot.activation_refs],
            "inclusion_reasons": {k: list(v) for k, v in snapshot.inclusion_reasons.items()},
        }
        return snapshot.model_copy(update={"projection_hash": _canonical(verification)})

    # -- carga autorizada -----------------------------------------------------

    def _load_self(self, self_assignment: Ref, scope: Scope) -> SelfAssignment:
        assignment = self._self_assignments.load(self_assignment, scope)
        if assignment is None:
            raise PermissionError(f"no hay SelfAssignment autorizado {self_assignment}")
        return assignment

    def _load_process(
        self, execution_scope: Ref, scope: Scope, assignment: SelfAssignment
    ) -> ProcessInstance:
        """El ExecutionScope es obligatorio: sin proceso, la proyección falla-cerrada."""
        process_ref = execution_scope
        if execution_scope.kind == "action_execution":
            if self._execution_processes is None:
                raise EvidenceError("action scope requires persisted ExecutionProcesses")
            parent = self._execution_processes.lookup_process(execution_scope, scope)
            if parent is None:
                raise EvidenceError(f"execution {execution_scope} has no authorized process")
            process_ref = parent
        process = self._processes.load(process_ref, scope)
        if process is None:
            raise EvidenceError(f"execution_scope {execution_scope} no resuelve a un proceso")
        participant = assignment.actor_ref in process.participant_refs
        participant2 = participant or assignment.ref in process.participant_refs
        if not participant2:
            raise PermissionError(f"{assignment.ref} no participa en {execution_scope}")
        return process

    def _load_machine(self, machine_ref: Ref, scope: Scope) -> MachineInstance:
        """Una máquina declarada pero inexistente detiene la proyección (fail-closed)."""
        instance = self._machine.load(machine_ref, scope)
        return instance

    def _machine_refs(self, assignment: SelfAssignment, process: ProcessInstance) -> list[Ref]:
        refs: list[Ref] = [assignment.machine_ref] if assignment.machine_ref is not None else []
        refs.extend(process.machine_refs)
        return list(dict.fromkeys(refs))

    def _authorized_evidence(
        self,
        execution_scope: Ref,
        scope: Scope,
        required: tuple[Ref, ...] = (),
    ) -> list[Observation]:
        """Observaciones citadas por la ejecución, autorizadas por scope del actor.

        Fail-closed: una observación citada pero ausente o caducada detiene la proyección.
        Nunca lee internos de máquina/proceso por el WorldData de negocio.
        """
        now = self._now()
        if now.tzinfo is None or now.utcoffset() != timedelta(0):
            raise EvidenceError("projection evidence clock must be UTC")
        refs = tuple(
            dict.fromkeys((*self._evidence_selection.observations_for(execution_scope, scope), *required))
        )
        observed: list[Observation] = []
        for ref in refs:
            obs = self._world_evidence.get_observation(ref, scope)
            if obs is None:
                raise EvidenceError(f"evidencia citada {ref} no está persistida")
            expected = self._evidence_selection.revision_for(execution_scope, ref, scope)
            if expected is None or expected != obs.revision:
                raise EvidenceError(f"evidence {ref} lacks matching pinned revision")
            if not self._fresh(obs, now):
                raise EvidenceError(f"evidencia {ref} está caducada u obsoleta (revisión {obs.revision})")
            observed.append(obs)
        return sorted(observed, key=lambda o: str(o.ref))

    @staticmethod
    def _fresh(obs: Observation, now: datetime) -> bool:
        return obs.observed_at <= now and not (obs.expires_at is not None and obs.expires_at <= now)

    def _allowed_actions(self, assignment: SelfAssignment, scope: Scope) -> tuple[Ref, ...]:
        """Self.can_perform declarado ∩ grants efectivos del assignment."""
        declared = list(self._self_declarations.declared_actions(assignment.self_definition_ref, scope))
        granted: set[str] = set()
        for capability in assignment.granted_capabilities:
            if capability.startswith("action:"):
                granted.add(capability[len("action:") :])
        allowed: list[Ref] = []
        for action_ref in declared:
            # Un grant "action:<id>" autoriza el ActionDoc declarado cuyo último componente es <id>.
            last = action_ref.id.rsplit(":", 1)[-1]
            if last in granted:
                allowed.append(action_ref)
        return tuple(sorted(allowed, key=lambda r: str(r)))

    def _goals_for(self, process: ProcessInstance, scope: Scope) -> list[GoalInstance]:
        refs = list(process.goal_refs)
        goals: list[GoalInstance] = []
        for ref in dict.fromkeys(refs):
            goal = self._goals.load(ref, scope)
            if goal is None:
                raise EvidenceError(f"goal {ref} no existe en {scope.client_id}")
            goals.append(goal)
        return goals

    def _knowledge_for(
        self, assignment: SelfAssignment, execution_scope: Ref, scope: Scope
    ) -> tuple[list[Ref], list[Ref]]:
        version_refs: list[Ref] = []
        activation_refs: list[Ref] = []
        for activation in self._knowledge.active_for(assignment.ref, execution_scope, scope):
            version_refs.append(activation.knowledge_version_ref)
            activation_refs.append(activation.ref)
        return version_refs, activation_refs

    @staticmethod
    def _machine_record(instance: MachineInstance) -> dict[str, JsonValue]:
        return {
            "ref": str(instance.ref),
            "definition_ref": str(instance.definition_ref),
            "definition_hash": instance.definition_hash,
            "state": instance.state,
            "revision": instance.revision,
            "variables": dict(instance.variables),
            "owner_ref": str(instance.owner_ref),
        }

    @staticmethod
    def _observation_record(obs: Observation) -> dict[str, JsonValue]:
        return {
            "ref": str(obs.ref),
            "value": dict(obs.value) if isinstance(obs.value, dict) else obs.value,
            "revision": obs.revision,
            "source_ref": str(obs.source_ref),
            "observed_at": obs.observed_at.isoformat(),
            "expires_at": obs.expires_at.isoformat() if obs.expires_at else None,
            "client_id": obs.scope.client_id,
        }

    @staticmethod
    def _inclusion_reasons(
        instances: list[MachineInstance],
        goals: list[GoalInstance],
        observations: list[Observation],
        versions: list[Ref],
    ) -> Mapping[str, tuple[str, ...]]:
        reasons: dict[str, tuple[str, ...]] = {}
        for instance in instances:
            reasons[str(instance.ref)] = (
                "machine-revision-fijada",
                f"source={instance.definition_ref!s}",
                f"hash={instance.definition_hash}",
                f"revision={instance.revision}",
            )
        for obs in observations:
            reasons[str(obs.ref)] = (
                "observation-citada",
                f"source={obs.source_ref!s}",
                f"revision={obs.revision}",
                f"observed_at={obs.observed_at.isoformat()}",
            )
        states = {instance.ref: instance.state for instance in instances}
        for goal in goals:
            reasons[str(goal.ref)] = (
                "goal-estado-observado",
                f"status={states[goal.machine_ref]}",
                f"source={goal.goal_definition_ref}",
                f"hash={goal.goal_definition_hash}",
                f"revision={goal.revision}",
                f"machine_ref={goal.machine_ref}",
            )
        for version in versions:
            reasons[str(version)] = ("knowledge-publicado-activo",)
        return reasons


class EvidenceError(Exception):
    """Evidencia citada faltante u obsoleta: fail-closed para autorización."""


__all__ = [
    "ContextProjector",
    "EvidenceError",
    "EvidenceSelection",
    "ExecutionProcesses",
    "KbSelfDeclarations",
    "SelfDeclarations",
    "SnapshotBuilder",
    "_canonical",
]
