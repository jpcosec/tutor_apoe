"""Scope y AccessScope: frontera tenant/cliente y autorización efectiva."""

from __future__ import annotations

from cognitive._base import FrozenModel
from ontology import Ref


class Scope(FrozenModel):
    """Frontera de datos: cliente/tenant con sujeto opcional.

    Nunca se acepta de argumentos del LLM; lo entrega el ensamblaje/canal autenticado.
    """

    client_id: str
    subject_ref: Ref | None = None


class AccessScope(Scope):
    """Scope + actor efectivo y capacidades ya resueltas por autorización."""

    actor_ref: Ref
    capabilities: frozenset[str] = frozenset()
