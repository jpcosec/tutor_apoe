"""Lifecycle de Knowledge: versiones durables y activaciones por consumidor (canonical §13).

Cubre: eligibilidad (solo published), dos consumidores activando versiones distintas sin
editar el documento, invalidación por retiro que anula activaciones existentes, invalidación
demorada (fail-closed ante evento tardío) y separación de vigencia vs activación.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from cognitive import KnowledgeActivation, KnowledgeVersion, Scope
from context.knowledge import (
    KnowledgeActivationsByVersion,
    KnowledgeError,
    KnowledgeLifecycle,
)
from ontology import Ref


def _ref(kind: str, key: str) -> Ref:
    return Ref.parse(f"{kind}:{key}")


def _scope(client: str = "tenant-a") -> Scope:
    return Scope(client_id=client)


def _version(key: str, status: str = "published", def_key: str = "KnowledgeDoc:k") -> KnowledgeVersion:
    return KnowledgeVersion(
        ref=_ref("knowledge_version", key),
        knowledge_definition_ref=_ref("kb", def_key),
        content_hash=f"h-{key}",
        status=status,  # type: ignore[arg-type]
        version="1.0",
        release_id="rel-1",
        created_at=datetime.now(UTC),
        scope=_scope(),
    )


class MemoryKnowledgeStore:
    """Implementación en memoria de KnowledgeStore + KnowledgeActivationsByVersion."""

    def __init__(self) -> None:
        self.versions: dict[str, KnowledgeVersion] = {}
        self.activations: dict[str, KnowledgeActivation] = {}

    def create_version(self, version: KnowledgeVersion) -> KnowledgeVersion:
        self.versions[version.ref.id] = version
        return version

    def load_version(self, ref: Ref, scope: Scope) -> KnowledgeVersion | None:
        return self.versions.get(ref.id)

    def create_activation(self, activation: KnowledgeActivation) -> KnowledgeActivation:
        self.activations[activation.ref.id] = activation
        return activation

    def load_activation(self, ref: Ref, scope: Scope) -> KnowledgeActivation | None:
        return self.activations.get(ref.id)

    def update_activation(self, activation: KnowledgeActivation) -> KnowledgeActivation:
        self.activations[activation.ref.id] = activation
        return activation

    def list_activations(
        self, self_assignment: Ref, execution_scope: Ref, scope: Scope
    ) -> tuple[KnowledgeActivation, ...]:
        return tuple(
            a
            for a in self.activations.values()
            if a.self_assignment_ref.id == self_assignment.id
            and a.execution_scope_ref.id == execution_scope.id
        )

    def list_activations_for_version(self, version_ref: Ref, scope: Scope) -> tuple[KnowledgeActivation, ...]:
        return tuple(a for a in self.activations.values() if a.knowledge_version_ref.id == version_ref.id)


def _lifecycle(
    store: MemoryKnowledgeStore, injections: KnowledgeActivationsByVersion | None = None
) -> KnowledgeLifecycle:
    return KnowledgeLifecycle(
        store,
        now=lambda: datetime.now(UTC),
        activations_by_version=injections or store,
    )


SELF = _ref("self_assignment", "self-1")
SELF2 = _ref("self_assignment", "self-2")
SCOPE_REF = _ref("process_instance", "exec-1")


def test_solo_eligible_se_activa() -> None:
    store = MemoryKnowledgeStore()
    store.create_version(_version("v1", "published"))
    lc = _lifecycle(store)
    act = lc.activate(_ref("knowledge_version", "v1"), SELF, SCOPE_REF, _scope())
    assert act.status == "active"


def test_no_elegible_rechaza_activacion() -> None:
    store = MemoryKnowledgeStore()
    store.create_version(_version("v1", "retired"))
    lc = _lifecycle(store)
    with pytest.raises(KnowledgeError):
        lc.activate(_ref("knowledge_version", "v1"), SELF, SCOPE_REF, _scope())


def test_dos_consumidores_versiones_distintas() -> None:
    """Dos roles activan conocimiento distinto sin editar el documento fuente."""
    store = MemoryKnowledgeStore()
    store.create_version(_version("v-a", "published", "KnowledgeDoc:ka"))
    store.create_version(_version("v-b", "published", "KnowledgeDoc:kb"))
    lc = _lifecycle(store)
    lc.activate(_ref("knowledge_version", "v-a"), SELF, SCOPE_REF, _scope())
    lc.activate(_ref("knowledge_version", "v-b"), SELF2, SCOPE_REF, _scope())

    a = lc.active_for(SELF, SCOPE_REF, _scope())
    b = lc.active_for(SELF2, SCOPE_REF, _scope())
    assert [x.knowledge_version_ref.id for x in a] == ["v-a"]
    assert [x.knowledge_version_ref.id for x in b] == ["v-b"]
    # el documento fuente no cambió
    assert store.versions["v-a"].status == "published"


def test_invalidate_revoca_activaciones_existentes() -> None:
    store = MemoryKnowledgeStore()
    store.create_version(_version("v1", "published"))
    lc = _lifecycle(store)
    lc.activate(_ref("knowledge_version", "v1"), SELF, SCOPE_REF, _scope())
    lc.activate(_ref("knowledge_version", "v1"), SELF2, SCOPE_REF, _scope())

    # retiro: se invalida la vigencia y las activaciones existentes
    store.versions["v1"] = _version("v1", "retired")
    invalidated = lc.invalidate(_ref("knowledge_version", "v1"), _scope())
    assert len(invalidated) == 2
    assert all(a.status == "invalidated" for a in invalidated)
    # ya no aparece en active_for
    assert lc.active_for(SELF, SCOPE_REF, _scope()) == ()


def test_invalidacion_demorada_fail_closed() -> None:
    """Un evento demorado: la activación sigue marcada activa en el store, pero la versión
    fue retirada y el projector re-valida vigencia fresca → no la devuelve."""
    store = MemoryKnowledgeStore()
    store.create_version(_version("v1", "published"))
    lc = _lifecycle(store)
    lc.activate(_ref("knowledge_version", "v1"), SELF, SCOPE_REF, _scope())
    # la versión se retira "después" (evento demorado), pero la activación no se tocó
    store.versions["v1"] = _version("v1", "retired")
    # active_for re-valida fresh → fail-closed
    assert lc.active_for(SELF, SCOPE_REF, _scope()) == ()


def test_eligibility_filtra_antes_de_seleccion() -> None:
    store = MemoryKnowledgeStore()
    store.create_version(_version("v1", "published"))
    store.create_version(_version("v2", "superseded"))
    lc = _lifecycle(store)
    elig = lc.eligible_versions((_ref("knowledge_version", "v1"), _ref("knowledge_version", "v2")), _scope())
    assert [v.ref.id for v in elig] == ["v1"]


def test_without_by_version_port_no_revoke() -> None:
    """Sin el port de enumeración por versión, invalidate no falla en silencio."""
    store = MemoryKnowledgeStore()
    lc = KnowledgeLifecycle(store, now=lambda: datetime.now(UTC))
    with pytest.raises(KnowledgeError):
        lc.invalidate(_ref("knowledge_version", "v1"), _scope())


def test_sql_activation_restart_and_current_revision(tmp_path: Path) -> None:
    pytest.importorskip("data")
    from data.machines import SqlKnowledgeStore
    from runtime.context.tests.projection_support import NOW, PROCESS, SCOPE, SELF, Substrate

    substrate = Substrate(tmp_path)
    version = _version("sql-v1").model_copy(update={"scope": SCOPE})
    substrate.knowledge.create_version(version)
    lifecycle = KnowledgeLifecycle(substrate.knowledge, now=lambda: NOW)
    first = lifecycle.activate(version.ref, SELF, PROCESS, SCOPE)
    restarted = KnowledgeLifecycle(SqlKnowledgeStore(substrate.store, substrate.privacy), now=lambda: NOW)
    second = restarted.activate(version.ref, SELF, PROCESS, SCOPE)
    assert second.revision == first.revision + 1
    other = restarted.activate(version.ref, Ref.parse("self_assignment:other"), PROCESS, SCOPE)
    assert other.ref != second.ref
    assert restarted.active_for(SELF, PROCESS, SCOPE) == (second,)
    assert restarted.active_for(Ref.parse("self_assignment:other"), PROCESS, SCOPE) == (other,)


def test_sql_retired_after_wait_without_invalidation_event(tmp_path: Path) -> None:
    pytest.importorskip("data")
    from sqlalchemy import update

    from data.machines import KnowledgeVersionRow
    from runtime.context.tests.projection_support import NOW, PROCESS, SCOPE, SELF, Substrate

    substrate = Substrate(tmp_path)
    version = _version("sql-v1").model_copy(update={"scope": SCOPE})
    substrate.knowledge.create_version(version)
    lifecycle = KnowledgeLifecycle(substrate.knowledge, now=lambda: NOW)
    active = lifecycle.activate(version.ref, SELF, PROCESS, SCOPE)
    # Persist lifecycle retirement as the SQL owner does; no invalidation event is delivered.
    retired = version.model_copy(update={"status": "retired"})
    with substrate.store.writing() as session:
        session.execute(
            update(KnowledgeVersionRow)
            .where(
                KnowledgeVersionRow.client_id == SCOPE.client_id,
                KnowledgeVersionRow.ref == str(version.ref),
            )
            .values(status="retired", payload=retired.model_dump(mode="json"))
        )
    assert substrate.knowledge.load_activation(active.ref, SCOPE) == active
    assert lifecycle.active_for(SELF, PROCESS, SCOPE) == ()
    with pytest.raises(KnowledgeError):
        lifecycle.activate(version.ref, SELF, PROCESS, SCOPE)


def test_sql_invalidation_enumerates_all_consumers(tmp_path: Path) -> None:
    pytest.importorskip("data")
    from runtime.context.tests.projection_support import NOW, PROCESS, SCOPE, SELF, Substrate

    substrate = Substrate(tmp_path)
    version = _version("sql-v1").model_copy(update={"scope": SCOPE})
    substrate.knowledge.create_version(version)
    lifecycle = KnowledgeLifecycle(
        substrate.knowledge,
        now=lambda: NOW,
        activations_by_version=substrate.knowledge,
    )
    lifecycle.activate(version.ref, SELF, PROCESS, SCOPE)
    lifecycle.activate(version.ref, Ref.parse("self_assignment:second"), PROCESS, SCOPE)
    invalidated = lifecycle.invalidate(version.ref, SCOPE)
    assert len(invalidated) == 2
    assert all(activation.status == "invalidated" for activation in invalidated)
    assert lifecycle.active_for(SELF, PROCESS, SCOPE) == ()
    for activation in invalidated:
        assert substrate.knowledge.load_activation(activation.ref, SCOPE) == activation
