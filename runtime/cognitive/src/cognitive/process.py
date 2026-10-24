"""Procesos: instancia semántica con identidad propia, no conversación."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cognitive._base import FrozenModel
from cognitive.scope import Scope
from ontology import Ref


class ProcessInstance(FrozenModel):
    """Lifecycle semántico; vive entre conversaciones y sirve a varios goals."""

    ref: Ref
    process_definition_ref: Ref
    process_definition_hash: str
    case_ref: Ref | None = None
    scope: Scope
    machine_refs: tuple[Ref, ...] = ()
    goal_refs: tuple[Ref, ...] = ()
    participant_refs: tuple[Ref, ...] = ()
    conversation_refs: tuple[Ref, ...] = ()
    revision: int = 0


@runtime_checkable
class ProcessStore(Protocol):
    """Persistencia tipada de ProcessInstance."""

    def create(self, instance: ProcessInstance) -> ProcessInstance: ...
    def load(self, ref: Ref, scope: Scope) -> ProcessInstance | None: ...
    def update(self, instance: ProcessInstance) -> ProcessInstance: ...
    def list_by_owner(self, owner: Ref, scope: Scope) -> tuple[ProcessInstance, ...]: ...
    def list_by_conversation(self, conversation: Ref, scope: Scope) -> tuple[ProcessInstance, ...]: ...
