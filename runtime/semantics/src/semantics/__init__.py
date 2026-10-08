"""Spec 15: la ontología del runtime; coordina KB, entidades, tools y el texto que ven los agentes."""

from semantics.entities import ENTITY_TAG, entity_type
from semantics.ontology import Ontology, Resolved, TurnSummaryLike, UnknownRef

__all__ = ["ENTITY_TAG", "Ontology", "Resolved", "TurnSummaryLike", "UnknownRef", "entity_type"]
