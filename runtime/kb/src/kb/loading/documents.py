"""De lo que entrega sldb a `Document` (spec 01 §7.1)."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from sldb import StructuredNLDoc

from kb.loading.sldb_gateway import LoadedDocument
from kb.model.document import Document, document_ref
from kb.payload import as_list, as_mapping, str_list
from kb.tags import is_blocked

_EDITORIAL_FIELDS = ("tags", "semantic_tags")


def build_document(
    loaded: LoadedDocument, model_ref: str, root: Path, blocked: list[str], content_hash: str = ""
) -> Document:
    editorial = _editorial_tags(loaded.payload)
    model_tags = sorted(set(loaded.semantic_tags) - set(editorial))
    all_tags = sorted({*model_tags, *editorial})
    return Document(
        ref=document_ref(loaded.model_name, loaded.name),
        name=loaded.name,
        model=loaded.model_name,
        model_ref=model_ref,
        ancestors=ancestors(loaded.model_type),
        family=getattr(loaded.model_type, "__family__", None),
        model_tags=model_tags,
        tags=editorial,
        all_tags=all_tags,
        path=_relative(loaded.path, root),
        payload=as_mapping(_json_safe(loaded.payload)) or {},
        eligible=not is_blocked(all_tags, blocked),
        content_hash=content_hash,
    )


def ancestors(model_type: type[StructuredNLDoc]) -> list[str]:
    """Las clases `StructuredNLDoc` por encima del modelo, de la más cercana a la más lejana."""
    return [
        cls.__name__
        for cls in model_type.__mro__[1:]
        if issubclass(cls, StructuredNLDoc) and cls is not StructuredNLDoc
    ]


def _editorial_tags(payload: dict[str, object]) -> list[str]:
    return sorted({tag for field in _EDITORIAL_FIELDS for tag in str_list(payload.get(field))})


def _json_safe(value: object) -> object:
    """Fechas de YAML a ISO 8601, para que el payload sea siempre serializable a JSON."""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if (mapping := as_mapping(value)) is not None:
        return {str(key): _json_safe(item) for key, item in mapping.items()}
    if (items := as_list(value)) is not None:
        return [_json_safe(item) for item in items]
    return value


def _relative(path: str, root: Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        return candidate.as_posix()
    try:
        return candidate.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return candidate.as_posix()
