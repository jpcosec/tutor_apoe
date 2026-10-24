"""Knowledge: versiones, activaciones, selector y persistencia tipada."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from cognitive._base import FrozenModel
from cognitive._time import Utc
from cognitive.scope import Scope
from ontology import Ref

KnowledgeVersionStatus = Literal["proposed", "validated", "published", "superseded", "retired"]
KnowledgeActivationStatus = Literal["candidate", "selected", "active", "invalidated"]


class KnowledgeVersion(FrozenModel):
    """Versión de conocimiento con vida propia (aprobación/publicación/vigencia)."""

    ref: Ref
    knowledge_definition_ref: Ref
    content_hash: str
    status: KnowledgeVersionStatus
    version: str
    release_id: str
    created_at: Utc
    scope: Scope

    @property
    def eligible(self) -> bool:
        """published admite nuevas activaciones; superseded/retired no."""
        return self.status == "published"


class KnowledgeActivation(FrozenModel):
    """Activación por consumidor + execution_scope; distinta de vigencia."""

    ref: Ref
    knowledge_version_ref: Ref
    self_assignment_ref: Ref
    execution_scope_ref: Ref
    scope: Scope
    status: KnowledgeActivationStatus = "candidate"
    activated_at: Utc | None = None
    invalidated_at: Utc | None = None
    revision: int = 0


class KnowledgeSelector(FrozenModel):
    """Selección declarativa de conocimiento; vacío = alcance explícito del consumidor."""

    model_names: tuple[str, ...] = ()
    tags_any: tuple[str, ...] = ()
    tags_all: tuple[str, ...] = ()
    relation_from: Ref | None = None
    projection_name: str | None = None


@runtime_checkable
class KnowledgeStore(Protocol):
    """Persistencia tipada de versiones y activaciones."""

    def create_version(self, version: KnowledgeVersion) -> KnowledgeVersion: ...
    def load_version(self, ref: Ref, scope: Scope) -> KnowledgeVersion | None: ...
    def create_activation(self, activation: KnowledgeActivation) -> KnowledgeActivation: ...
    def load_activation(self, ref: Ref, scope: Scope) -> KnowledgeActivation | None: ...
    def update_activation(self, activation: KnowledgeActivation) -> KnowledgeActivation: ...
    def list_activations(
        self, self_assignment: Ref, execution_scope: Ref, scope: Scope
    ) -> tuple[KnowledgeActivation, ...]: ...

    def list_activations_for_version(
        self, version_ref: Ref, scope: Scope
    ) -> tuple[KnowledgeActivation, ...]: ...
