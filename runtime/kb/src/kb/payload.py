"""Lectura tipada de valores dinámicos (payloads de sldb, YAML): un solo lugar que estrecha tipos."""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast


def as_list(value: object) -> list[object] | None:
    return cast("list[object]", value) if isinstance(value, list | tuple) else None


def as_mapping(value: object) -> dict[str, object] | None:
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def str_list(value: object) -> list[str]:
    """Una lista de strings; cualquier otra cosa es la lista vacía."""
    items = as_list(value)
    return [str(item) for item in items] if items is not None else []


def children(value: object) -> Iterator[object]:
    """Los valores de un mapa o los elementos de una lista; nada para un escalar."""
    mapping = as_mapping(value)
    if mapping is not None:
        yield from mapping.values()
        return
    yield from as_list(value) or []


def walk_strings(value: object) -> Iterator[str]:
    """Todos los strings de una estructura anidada de mapas y listas."""
    if isinstance(value, str):
        yield value
        return
    for child in children(value):
        yield from walk_strings(child)
