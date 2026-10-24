"""Paquete hoja `ontology` (spec 13): cómo se identifica y se refiere cualquier objeto del sistema."""

from ontology.base import OntologyObject
from ontology.canonical import canonical_json
from ontology.episode import Episode, cause_problems, nesting_problems
from ontology.grammar import (
    DOC_KEY_RE,
    EDITORIAL_TAG_RE,
    IDENTIFIER_RE,
    SEMANTIC_TAG_RE,
    DocKey,
    EditorialTag,
    Identifier,
    ModelName,
    SemanticTag,
)
from ontology.ids import new_id
from ontology.provenance import Provenance
from ontology.ref import Kind, Ref, RefFormatError, RefWithoutRelease
from ontology.verify import Resolver, VerifyReport, verify_refs

__all__ = [
    "DOC_KEY_RE",
    "EDITORIAL_TAG_RE",
    "IDENTIFIER_RE",
    "SEMANTIC_TAG_RE",
    "DocKey",
    "EditorialTag",
    "Episode",
    "Identifier",
    "Kind",
    "ModelName",
    "OntologyObject",
    "Provenance",
    "Ref",
    "RefFormatError",
    "RefWithoutRelease",
    "Resolver",
    "SemanticTag",
    "VerifyReport",
    "canonical_json",
    "cause_problems",
    "nesting_problems",
    "new_id",
    "verify_refs",
]
