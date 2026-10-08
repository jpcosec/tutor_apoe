"""Base congelada del contrato canónico.

frozen=True + extra=forbid + copia defensiva en construcción; además cada
contenedor JSON (dict/list) del modelo se sustituye por variantes inmutables
profundas: mutar `modelo.campo[...]`, `+=`, `*=`, `append`, etc. lanza TypeError,
incluso en dicts/listas anidadas. `model_copy(update=...)` revalida el update
(construyendo un modelo nuevo) y vuelve a congelar; `copy`/`deepcopy` devuelven
el mismo objeto inmutable.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any, Self, cast

from pydantic import BaseModel, ConfigDict


class _ImmutableDict(dict[str, Any]):
    """dict que rechaza toda mutación directa o por operador; sigue siendo dict."""

    def __setitem__(self, key: Any, value: Any) -> None:
        raise TypeError("dict congelado no admite asignación")

    def __delitem__(self, key: Any) -> None:
        raise TypeError("dict congelado no admite borrado")

    def __ior__(self, other: Any) -> _ImmutableDict:
        raise TypeError("dict congelado no admite mutación")

    def clear(self) -> None:
        raise TypeError("dict congelado no admite mutación")

    def pop(self, *args: Any) -> Any:
        raise TypeError("dict congelado no admite mutación")

    def popitem(self) -> tuple[Any, Any]:
        raise TypeError("dict congelado no admite mutación")

    def setdefault(self, *args: Any) -> Any:
        raise TypeError("dict congelado no admite mutación")

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("dict congelado no admite mutación")

    def __copy__(self) -> _ImmutableDict:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> _ImmutableDict:
        return self

    def __reduce__(self) -> tuple[type, tuple[dict[str, Any]]]:
        # permite copy/pickle reconstruyendo un dict congelado (no un dict mutable).
        return (_ImmutableDict, (dict(self),))


class _ImmutableList(list[Any]):
    """list que rechaza toda mutación directa o por operador; sigue siendo list."""

    def __setitem__(self, index: Any, value: Any) -> None:
        raise TypeError("list congelado no admite asignación")

    def __delitem__(self, index: Any) -> None:
        raise TypeError("list congelado no admite borrado")

    def __iadd__(self, other: Any) -> _ImmutableList:
        raise TypeError("list congelado no admite mutación")

    def __imul__(self, other: Any) -> _ImmutableList:
        raise TypeError("list congelado no admite mutación")

    def append(self, value: Any) -> None:
        raise TypeError("list congelado no admite mutación")

    def extend(self, values: Any) -> None:
        raise TypeError("list congelado no admite mutación")

    def insert(self, index: Any, value: Any) -> None:
        raise TypeError("list congelado no admite mutación")

    def remove(self, value: Any) -> None:
        raise TypeError("list congelado no admite mutación")

    def pop(self, *args: Any) -> Any:
        raise TypeError("list congelado no admite mutación")

    def clear(self) -> None:
        raise TypeError("list congelado no admite mutación")

    def reverse(self) -> None:
        raise TypeError("list congelado no admite mutación")

    def sort(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("list congelado no admite mutación")

    def __copy__(self) -> _ImmutableList:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> _ImmutableList:
        return self

    def __reduce__(self) -> tuple[type, tuple[list[Any]]]:
        return (_ImmutableList, (list(self),))


def _freeze(value: Any) -> Any:
    """Sustituye recursivamente dict/list/tuple por variantes inmutables.

    Los valores que ya son inmutables (DTOs frozen, escalares, `_ImmutableDict`/
    `_ImmutableList`) se devuelven tal cual; las tuplas se reconstruyen con TODOS
    sus elementos recursivamente congelados (una tupla anidada puede contener
    dict/list, que de otro modo quedarían mutables dentro de la tupla inmutable).
    """
    if isinstance(value, (_ImmutableDict, _ImmutableList)):
        return value
    if isinstance(value, dict):
        source = cast(dict[str, Any], value)
        frozen: dict[str, Any] = {}
        for key, item in source.items():
            frozen[key] = _freeze(item)
        return _ImmutableDict(frozen)
    if isinstance(value, list):
        seq = cast(list[Any], value)
        items: list[Any] = [_freeze(item) for item in seq]
        return _ImmutableList(items)
    if isinstance(value, tuple):
        group = cast(tuple[Any, ...], value)
        return tuple(_freeze(item) for item in group)
    return value


def _freeze_instance(model: BaseModel) -> None:
    for field in type(model).model_fields:
        object.__setattr__(model, field, _freeze(getattr(model, field)))


def freeze_json_snapshot(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Congela en profundidad un snapshot JSON (Mappings anidados), PÚBLICO y canónico.

    Sustituto oficial del `_deep_freeze` privado de cada worker de proyección:
    dict/list anidados pasan a variantes que rechazan toda mutación; tuplas
    (incluidas tuplas anidadas con dict/list dentro) se reconstruyen congeladas.
    Idempotente: un snapshot ya congelado se devuelve tal cual. La clave de
    índice es siempre `str(ref)` del DTO (proyección/context).
    """
    return cast(Mapping[str, Any], _freeze(value))


class FrozenModel(BaseModel):
    """Modelo inmutable con contenedores JSON profundamente inmutables."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    def __init__(self, /, **data: Any) -> None:
        super().__init__(**{key: copy.deepcopy(value) for key, value in data.items()})
        _freeze_instance(self)

    def model_copy(
        self, *, update: Mapping[str, Any] | None = None, deep: bool = False
    ) -> Self:
        if update:
            data: dict[str, Any] = {
                field: getattr(self, field) for field in type(self).model_fields
            }
            data.update(update)
            return type(self)(**data)  # revalida (model_copy no valida por defecto)
        return super().model_copy(update=None, deep=deep)
