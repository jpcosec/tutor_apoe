"""Las entidades que declara la KB como `EntityDoc` (spec 15 §4, O2)."""

from __future__ import annotations

from typing import Any, cast

from kb import Document, KnowledgeBase
from ontology import Ref
from tools import EntityType, EpisodeSpec

ENTITY_TAG = "type.knowledge.entity"


def entity_documents(kb: KnowledgeBase) -> list[Document]:
    return [d for d in kb.eligible() if ENTITY_TAG in d.model_tags]


def entity_type(document: Document) -> EntityType:
    payload = document.payload
    columns = cast(list[dict[str, Any]], payload.get("fields") or [])
    return EntityType(
        ref=Ref(kind="entity", id=str(payload["name"])),
        name=str(payload["name"]),
        key=str(payload["key"]),
        fields={str(c["name"]): c["type"] for c in columns},
        personal_fields=frozenset(str(c["name"]) for c in columns if c.get("personal")),
        subject_linked=bool(payload.get("subject_linked", True)),
        descriptions={str(c["name"]): str(c.get("description") or "") for c in columns},
        episode=_episode(payload.get("episode")),
    )


def _episode(raw: object) -> EpisodeSpec | None:
    """`episode: {state_field, closing}` del `EntityDoc`, si la entidad lo declara."""
    return EpisodeSpec.model_validate(raw) if isinstance(raw, dict) else None
