"""Norma de identificadores, tags y referencias (spec 13 §4.0).

`:` solo separa un namespace de lo que nombra; `.` solo expresa jerarquía; `@` solo
introduce un release. Todo campo que no es texto libre se declara con estos tipos.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import StringConstraints

IDENTIFIER = r"[a-z0-9][a-z0-9_-]*"
MODEL_NAME = r"[A-Z][A-Za-z0-9]*"
NAMESPACE = r"[a-z][a-z0-9_]*"
SEGMENT = IDENTIFIER
DOC_KEY = rf"{MODEL_NAME}:{IDENTIFIER}"
SEMANTIC_TAG = rf"{SEGMENT}(?:\.{SEGMENT})*"
EDITORIAL_TAG = rf"{NAMESPACE}(?::{SEGMENT}(?:\.{SEGMENT})*)?"

IDENTIFIER_RE = re.compile(rf"^{IDENTIFIER}$")
MODEL_NAME_RE = re.compile(rf"^{MODEL_NAME}$")
DOC_KEY_RE = re.compile(rf"^{DOC_KEY}$")
SEMANTIC_TAG_RE = re.compile(rf"^{SEMANTIC_TAG}$")
EDITORIAL_TAG_RE = re.compile(rf"^{EDITORIAL_TAG}$")

Identifier = Annotated[str, StringConstraints(pattern=rf"^{IDENTIFIER}$")]
ModelName = Annotated[str, StringConstraints(pattern=rf"^{MODEL_NAME}$")]
DocKey = Annotated[str, StringConstraints(pattern=rf"^{DOC_KEY}$")]
SemanticTag = Annotated[str, StringConstraints(pattern=rf"^{SEMANTIC_TAG}$")]
EditorialTag = Annotated[str, StringConstraints(pattern=rf"^{EDITORIAL_TAG}$")]


def first_invalid(value: str, pattern: re.Pattern[str]) -> int | None:
    """Posición del primer carácter que impide que `value` cumpla `pattern`; None si cumple."""
    if pattern.match(value):
        return None
    for end in range(len(value), 0, -1):
        if _prefix_fits(value[:end], pattern):
            return end
    return 0


def _prefix_fits(prefix: str, pattern: re.Pattern[str]) -> bool:
    return pattern.match(prefix) is not None
