"""`check-kb` (spec 03 §6.5): la KB y el catálogo declaran las mismas tools con los mismos parámetros."""

from __future__ import annotations

import json
from typing import cast

from kb import Document, KnowledgeBase
from tools.runner import ToolCatalog

TOOL_TAG = "type.knowledge.tool"


def check_kb(kb: KnowledgeBase, catalog: ToolCatalog) -> list[str]:
    problems: list[str] = []
    for document in (d for d in kb.eligible() if TOOL_TAG in d.model_tags):
        name, properties = _declared(document)
        tool = catalog.get(name) if name else None
        if tool is None:
            problems.append(f"{document.key}: la tool {name!r} no está en el catálogo")
            continue
        code = set(type(tool).Args.model_fields)
        if properties != code:
            problems.append(f"{document.key}: parámetros KB {sorted(properties)} ≠ código {sorted(code)}")
    return problems


def _declared(document: Document) -> tuple[str | None, set[str]]:
    """Nombre y parámetros que ve la LLM; en una tool de operación, sus `inputs` (14 §6.7)."""
    if document.payload.get("kinds"):  # tool de evento: su esquema lo arma el runtime
        return str(document.payload.get("name") or "") or None, {"kind", "payload", "due_at"}
    if document.payload.get("entity"):
        inputs = cast(list[object], document.payload.get("inputs") or [])
        names = {str(i) for i in inputs}
        return str(document.payload.get("name") or "") or None, names
    raw = document.payload.get("parameters")
    spec = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(spec, dict):
        return None, set()
    params = spec.get("parameters") or {}  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    properties = params.get("properties") or {}  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return spec.get("name"), set(properties)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportUnknownVariableType]
