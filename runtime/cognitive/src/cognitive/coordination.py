"""Coordinación entre máquinas: reglas declaradas, entrega y reporte."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from pydantic import Field

from cognitive._base import FrozenModel
from ontology import Ref

if TYPE_CHECKING:
    from cognitive.events import Event

TargetStatus = Literal["delivered", "rejected", "failed", "no_target"]
DeliveryStatus = Literal["delivered", "partial", "no_target", "rejected"]


class TargetSelector(FrozenModel):
    """Selección de destinatarios; owner_relation + machine_ref opcional."""

    owner_relation: str
    machine_ref: Ref | None = None


class CoordinationRuleDoc(FrozenModel):
    """Regla declarada: fuente -> selector -> evento destino con bindings."""

    id: str
    source_machine_ref: Ref
    source_event_type: str
    target_selector: TargetSelector
    target_event_type: str
    payload_bindings: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    max_hops: int = 32
    wait_for_creation: bool = False
    retry_until: str | None = None  # ISO UTC; reintento solo si la regla espera creación


class TargetResult(FrozenModel):
    """Resultado por destinatario; attempted/delivered/rejected se derivan de aquí."""

    target_ref: Ref
    status: TargetStatus
    evidence_refs: tuple[Ref, ...] = ()
    error_code: str | None = None
    retryable: bool = False
    retry_until: str | None = None


class DeliveryReport(FrozenModel):
    """Reporte de entrega; no hay segundos contadores independientes."""

    event_id: str
    target_results: tuple[TargetResult, ...] = ()
    hops: int = 0
    causal_chain: tuple[str, ...] = ()
    status: DeliveryStatus = "rejected"
    correlation_id: str = ""
    causation_id: str | None = None

    @property
    def attempted_targets(self) -> tuple[Ref, ...]:
        return tuple(r.target_ref for r in self.target_results if r.status != "no_target")

    @property
    def delivered_targets(self) -> tuple[Ref, ...]:
        return tuple(r.target_ref for r in self.target_results if r.status == "delivered")

    @property
    def rejected_targets(self) -> tuple[Ref, ...]:
        return tuple(r.target_ref for r in self.target_results if r.status in ("rejected", "failed"))


@runtime_checkable
class Coordinator(Protocol):
    """Entrega durable de eventos a máquinas destino; dedupe por inbox."""

    def deliver(self, event: Event) -> DeliveryReport: ...
