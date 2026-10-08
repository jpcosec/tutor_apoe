"""DTOs de eventos, observaciones y recepción externa (api-canonica §contratos comunes)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from cognitive._base import FrozenModel
from cognitive._time import Utc
from cognitive.jsons import JsonValue
from cognitive.scope import Scope
from ontology import Ref


class Event(FrozenModel):
    """Evento dirigido a una máquina; payload validado por JSON schema registrado."""

    id: str
    type: str
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    scope: Scope
    owner_ref: Ref
    source_ref: Ref
    occurred_at: Utc
    correlation_id: str
    causation_id: str | None = None


class Observation(FrozenModel):
    """Hecho observado (World.Data o World.External) usado como evidencia."""

    ref: Ref
    value: JsonValue
    source_ref: Ref
    observed_at: Utc
    revision: str
    expires_at: Utc | None = None
    scope: Scope


class ExternalReceipt(FrozenModel):
    """Resultado de una invocación externa; estado observado, nunca confirmado por comando local.

    `status` es el enum del contrato (accepted/confirmed/rejected/pending/unknown);
    NO se confunde con `ActionResult.status`. `revision` habilita CAS en
    reconcile_receipt (client_id+ref únicos).
    """

    ref: Ref
    invocation_id: str
    operation: str
    status: Literal["pending", "accepted", "confirmed", "rejected", "unknown"]
    provider_ref: Ref | None = None
    observed_at: Utc
    revision: str
    payload: JsonValue = None
    scope: Scope
