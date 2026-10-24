"""Lectura de los dos archivos autoritativos del índice (spec 01 §3.6): `store_index` y `models/<M>`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from kb.model.catalog import ModelInfo
from kb.payload import str_list

_BUILTIN_PACKAGES = ("sldb.", "pron.")


def registered_models(store: Path) -> list[ModelInfo]:
    """Los modelos que registra el store, ordenados por nombre (C3: no usa `path`)."""
    index = _read(store / "core" / "store_index.yaml")
    entries: list[dict[str, Any]] = index.get("models") or []
    return sorted((_model_info(store, entry) for entry in entries), key=lambda m: m.name)


def is_builtin_ref(model_ref: str) -> bool:
    return model_ref.startswith(_BUILTIN_PACKAGES)


def _model_info(store: Path, entry: dict[str, Any]) -> ModelInfo:
    name = str(entry["name"])
    detail = _read(store / "core" / "models" / f"{name}.yaml")
    model_ref = str(detail.get("model_ref") or entry["model_ref"])
    return ModelInfo(
        name=name,
        model_ref=model_ref,
        base_models=str_list(detail.get("base_models")),
        family=detail.get("family"),
        semantic_tags=sorted(str_list(detail.get("semantics"))),
        documents_count=int(detail.get("documents_count") or 0),
        builtin=is_builtin_ref(model_ref),
    )


def _read(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
