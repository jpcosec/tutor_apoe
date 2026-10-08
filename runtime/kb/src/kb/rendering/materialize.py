"""Render de un documento y materialización determinista de la KB elegible (spec 01 §6.1, §6.2)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from kb.model.document import Document

EXCLUDED_MODELS = ("RelationDoc", "RelationTypeDoc")
EXCLUDED_TAGS = ("type.kb.category", "type.kb.reference", "type.kb.tool_test")
NO_FAMILY = ""


def materialize(eligible: list[Document], order: list[str], render: Callable[[Document], str]) -> str:
    groups = _groups([d for d in eligible if _included(d)])
    lines = [f"# BASE DE CONOCIMIENTO ({sum(len(g) for g in groups.values())} documentos)", ""]
    for family in _group_order(groups, order):
        lines += [f"## {family or '(sin familia)'}", ""]
        for document in sorted(groups[family], key=lambda d: (d.model.encode(), d.name.encode())):
            lines += [f"### {document.key}", "", strip_frontmatter(render(document)).strip("\n"), ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def strip_frontmatter(text: str) -> str:
    """Quita el bloque `---` inicial una sola vez; sin cierre, no quita nada (§6.2)."""
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        return text
    for index in range(1, len(lines)):
        if lines[index] == "---":
            return "\n".join(lines[index + 1 :])
    return text


def _included(document: Document) -> bool:
    return document.model not in EXCLUDED_MODELS and not set(EXCLUDED_TAGS) & set(document.model_tags)


def _groups(documents: list[Document]) -> dict[str, list[Document]]:
    groups: dict[str, list[Document]] = defaultdict(list)
    for document in documents:
        groups[document.family or NO_FAMILY].append(document)
    return dict(groups)


def _group_order(groups: dict[str, list[Document]], order: list[str]) -> list[str]:
    listed = [family for family in order if family in groups and family != NO_FAMILY]
    rest = sorted((f for f in groups if f not in listed and f != NO_FAMILY), key=str.encode)
    return listed + rest + ([NO_FAMILY] if NO_FAMILY in groups else [])
