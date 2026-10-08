"""Reglas de tags: forma (13 §4.0), descendencia por segmentos y elegibilidad (spec 01 §4.4, §7.1)."""

from __future__ import annotations

from collections.abc import Iterable

from ontology import EDITORIAL_TAG_RE, SEMANTIC_TAG_RE

RESERVED_NAMESPACES = ("type", "representation", "source")


def is_under(tag: str, ancestor: str) -> bool:
    """`tag` es `ancestor` o desciende de él partiendo por `.` (`a.b` no cubre `a.bx`)."""
    return tag == ancestor or tag.startswith(ancestor + ".")


def is_blocked(tags: Iterable[str], blocked: Iterable[str]) -> bool:
    blocked_list = list(blocked)
    return any(is_under(tag, b) for tag in tags for b in blocked_list)


def is_editorial(tag: str) -> bool:
    """Forma de tag editorial de 13 §4.0 y namespace no reservado a la semántica de modelo."""
    return EDITORIAL_TAG_RE.match(tag) is not None and namespace(tag) not in RESERVED_NAMESPACES


def check_query_tag(tag: str) -> None:
    """`by_tag` acepta un tag editorial o uno semántico; cualquier otra cosa es `ValueError`."""
    if not (EDITORIAL_TAG_RE.match(tag) or SEMANTIC_TAG_RE.match(tag)):
        raise ValueError(f"tag inválido para consultar: {tag!r}")


def namespace(tag: str) -> str:
    return tag.split(":", 1)[0]
