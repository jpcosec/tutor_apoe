"""Lifecycle de Knowledge: versiones durables y activaciones por consumidor (api-canonica §13).

Separa la vigencia del documento (``KnowledgeVersion.status``) de la activación por
consumidor + execution_scope (``KnowledgeActivation``). ``eligible`` (``published``) admite
nuevas activaciones; ``superseded``/``retired`` no. Revocar una versión invalida las
activaciones existentes, y toda activación se re-valida contra el lifecycle vigente antes
de usarse (fail-closed ante eventos tardíos).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime
from typing import Protocol, runtime_checkable

from cognitive import (
    KnowledgeActivation,
    KnowledgeSelector,
    KnowledgeStore,
    KnowledgeVersion,
    Scope,
)
from kb.model.document import Document
from ontology import Ref


class KnowledgeError(Exception):
    """Error semántico de Knowledge lifecycle."""


@runtime_checkable
class KnowledgeActivationsByVersion(Protocol):
    """Port neutral que la persistencia SQL implementa: enumera activaciones por versión.

    La `KnowledgeStore` no lo cubre; es independiente del consumidor/execution_scope.
    (port solicitado en /tmp/canonical-projection-needs.md).
    """

    def list_activations_for_version(
        self, version_ref: Ref, scope: Scope
    ) -> tuple[KnowledgeActivation, ...]: ...


class KnowledgeProjection(Protocol):
    """Canonical declaration facade, including actual model registry ancestry."""

    def project(self, selector: KnowledgeSelector | None = None) -> tuple[Document, ...]: ...


class KnowledgeLifecycle:
    """Vigencia y activación de conocimiento sobre un `KnowledgeStore` neutral inyectado."""

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        now: Callable[[], datetime],
        activations_by_version: KnowledgeActivationsByVersion | None = None,
    ) -> None:
        self._store = store
        self._now = now
        self._by_version = activations_by_version

    # -- vigencia (documento) -------------------------------------------------

    def load_version(self, ref: Ref, scope: Scope) -> KnowledgeVersion | None:
        return self._store.load_version(ref, scope)

    def load_activation(self, ref: Ref, scope: Scope) -> KnowledgeActivation | None:
        return self._store.load_activation(ref, scope)

    def eligible_versions(self, version_refs: tuple[Ref, ...], scope: Scope) -> tuple[KnowledgeVersion, ...]:
        """Versiones aún elegibles (published) entre los candidatos, en orden estable."""
        out: list[KnowledgeVersion] = []
        for ref in dict.fromkeys(version_refs):
            version = self._store.load_version(ref, scope)
            if version is not None and version.eligible:
                out.append(version)
        return tuple(sorted(out, key=lambda v: str(v.ref)))

    # -- activación (por consumidor) -----------------------------------------

    def activate(
        self,
        version_ref: Ref,
        self_assignment: Ref,
        execution_scope: Ref,
        scope: Scope,
    ) -> KnowledgeActivation:
        """Activa una versión para un consumidor; rechaza si la versión no es elegible."""
        version = self._store.load_version(version_ref, scope)
        if version is None:
            raise KnowledgeError(f"versión {version_ref} no existe en {scope.client_id}")
        if not version.eligible:
            raise KnowledgeError(
                f"versión {version_ref} no es elegible (status={version.status}); requiere published"
            )
        now = self._now()
        ref = self._activation_ref(self_assignment, execution_scope, version_ref)
        existing = self._store.load_activation(ref, scope)
        if existing is not None:
            return self._store.update_activation(
                existing.model_copy(
                    update={
                        "status": "active",
                        "activated_at": now,
                        "invalidated_at": None,
                    }
                )
            )
        return self._store.create_activation(
            KnowledgeActivation(
                ref=ref,
                knowledge_version_ref=version_ref,
                self_assignment_ref=self_assignment,
                execution_scope_ref=execution_scope,
                scope=scope,
                status="active",
                activated_at=now,
                revision=0,
            )
        )

    def invalidate(self, version_ref: Ref, scope: Scope) -> tuple[KnowledgeActivation, ...]:
        """Revoca una versión: invalida las activaciones existentes que la referencian.

        Requiere el port `KnowledgeActivationsByVersion` (persistencia SQL) para enumerar
        por versión; sin él, no se puede revocar (error, no fallback silencioso).
        """
        if self._by_version is None:
            raise KnowledgeError(
                "no hay KnowledgeActivationsByVersion inyectado; no se puede revocar por versión"
            )
        affected = [
            a
            for a in self._by_version.list_activations_for_version(version_ref, scope)
            if a.knowledge_version_ref == version_ref and a.status == "active"
        ]
        invalidated: list[KnowledgeActivation] = []
        for activation in affected:
            invalidated.append(
                self._store.update_activation(
                    activation.model_copy(
                        update={
                            "status": "invalidated",
                            "invalidated_at": self._now(),
                        }
                    )
                )
            )
        return tuple(sorted(invalidated, key=lambda a: str(a.ref)))

    def active_for(
        self, self_assignment: Ref, execution_scope: Ref, scope: Scope
    ) -> tuple[KnowledgeActivation, ...]:
        """Activaciones de un consumidor, re-validando vigencia fresca ante uso.

        Aunque una activación siga en status `active`, si la versión ya no es elegible
        (superseded/retired) NO se devuelve: fail-closed ante eventos tardíos.
        """
        fresh: list[KnowledgeActivation] = []
        for activation in self._store.list_activations(self_assignment, execution_scope, scope):
            if activation.status != "active":
                continue
            version = self._store.load_version(activation.knowledge_version_ref, scope)
            if version is not None and version.eligible:
                fresh.append(activation)
        return tuple(sorted(fresh, key=lambda a: str(a.ref)))

    # -- proyecto -------------------------------------------------------------

    def select(self, selector: KnowledgeSelector, declarations: KnowledgeProjection) -> tuple[str, ...]:
        """Use the canonical facade's registered ancestry and scoped selector semantics."""
        return tuple(document.key for document in declarations.project(selector))

    # -- internals ------------------------------------------------------------

    @staticmethod
    def _activation_ref(self_assignment: Ref, execution_scope: Ref, version_ref: Ref) -> Ref:
        digest = hashlib.sha256(
            f"{self_assignment!s}|{execution_scope!s}|{version_ref!s}".encode()
        ).hexdigest()[:24]
        return Ref(kind="knowledge_activation", id=f"{base(self_assignment)}-{digest}")


def base(ref: Ref) -> str:
    return ref.id.split(":")[-1].split("~")[0]


__all__ = ["KnowledgeActivationsByVersion", "KnowledgeError", "KnowledgeLifecycle", "KnowledgeProjection"]
