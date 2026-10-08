"""Revisión humana durable: ReviewRequest y su puerto de persistencia."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from cognitive._base import FrozenModel
from cognitive._time import Utc
from cognitive.actions import ActionError
from cognitive.jsons import JsonObject, JsonValue
from cognitive.scope import Scope
from ontology import Ref

ReviewRequestStatus = Literal["requested", "assigned", "reviewing", "resolved", "expired"]


class ReviewRequest(FrozenModel):
    """Revisión humana; enum distinto de ActionResult y de action execution."""

    ref: Ref
    execution_ref: Ref
    action_ref: Ref
    status: ReviewRequestStatus = "requested"
    assignee_ref: Ref | None = None
    input_schema: JsonObject | None = None
    output_schema: JsonObject | None = None
    inputs: JsonObject | None = None
    revision: int = 0
    scope: Scope
    created_at: Utc
    assigned_at: Utc | None = None
    reviewed_at: Utc | None = None
    resolver_evidence: tuple[Ref, ...] = ()


class ReviewResolution(FrozenModel):
    """Evento producido al resolver; no iguala enums de ActionExecution."""

    review_ref: Ref
    execution_ref: Ref
    assignee_ref: Ref
    output: JsonValue | None = None
    error: ActionError | None = None
    revision: int
    resolved_at: Utc
    scope: Scope
    evidence_refs: tuple[Ref, ...] = ()


@runtime_checkable
class ReviewRequestStore(Protocol):
    """Persistencia durable de review requests con CAS por revision."""

    def create(self, request: ReviewRequest) -> ReviewRequest: ...
    def assign(self, ref: Ref, assignee: Ref, expected_revision: int, scope: Scope) -> ReviewRequest: ...
    def start(self, ref: Ref, expected_revision: int, scope: Scope) -> ReviewRequest: ...
    def resolve(
        self, resolution: ReviewResolution, expected_revision: int, scope: Scope
    ) -> ReviewResolution: ...
    def expire(self, ref: Ref, expected_revision: int, scope: Scope) -> ReviewRequest: ...
    def get(self, ref: Ref, scope: Scope) -> ReviewRequest | None: ...
