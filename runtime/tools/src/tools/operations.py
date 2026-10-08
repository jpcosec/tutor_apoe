"""Las operaciones de bajo nivel (14 §6.7): genéricas sobre una entidad, sin nombres de negocio.

Son la mitad cruda de las primitivas `records.*` (03 §4.5). Una tool no las llama directo: pasa
por `Primitives.records`, que además exige que la entidad esté en `writes`, marca el episodio y
deja la llamada en la auditoría. Por eso no se exportan desde `tools`.
"""

from __future__ import annotations

import logging
import statistics
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Literal, Protocol

from tools.contract import ToolError
from tools.entity import EntityType

log = logging.getLogger(__name__)

Aggregate = Literal["count", "sum", "mean", "min", "max"]


class StoredRow(Protocol):
    @property
    def key(self) -> str: ...
    @property
    def fields(self) -> dict[str, object]: ...


class RecordsPort(Protocol):
    """Lo que las operaciones usan del almacén de 02; lo cumple `SqlStore`."""

    def find_records(
        self,
        record_type: str,
        session_id: str | None,
        key: str | None,
        where: Mapping[str, object],
        newest_first: bool = False,
    ) -> Sequence[StoredRow]: ...
    def put_record(
        self, record_type: str, key: str, fields: dict[str, object], session_id: str | None = None
    ) -> int: ...


AGGREGATES: dict[Aggregate, Callable[[list[float]], float | int | None]] = {
    "count": len,
    "sum": lambda values: sum(values),
    "mean": lambda values: statistics.fmean(values) if values else None,
    "min": lambda values: min(values, default=None),
    "max": lambda values: max(values, default=None),
}


def personal_filters(entity: EntityType, fields: Iterable[str]) -> list[str]:
    """Los campos personales entre los filtros: van a la bóveda y no se filtran (02, A12). La clave
    sí, porque se busca por su HMAC."""
    return sorted(f for f in set(fields) & entity.personal_fields if f != entity.key)


def read(
    port: RecordsPort,
    entity: EntityType,
    where: Mapping[str, object],
    subject: str | None,
    newest_first: bool = False,
) -> list[dict[str, object]]:
    """Todas las filas que cumplen el filtro (C7): nunca elige una."""
    personal = personal_filters(entity, where)
    if personal:
        log.error("%s: filtro por campos personales %s (02)", entity.name, personal)
        raise ToolError("defect")
    key = where.get(entity.key)
    filters = {f: v for f, v in where.items() if f != entity.key}
    found = None if key is None else str(key)
    rows = port.find_records(entity.name, subject, found, filters, newest_first)
    return [{entity.key: row.key, **row.fields} for row in rows]


def write(
    port: RecordsPort, entity: EntityType, key: str, fields: Mapping[str, object], subject: str | None
) -> dict[str, object]:
    """Crea o actualiza la fila de la clave, sin pisar los campos que no vienen (idempotente)."""
    current = port.find_records(entity.name, subject, key, {})
    merged = {**(current[0].fields if current else {}), **fields}
    port.put_record(entity.name, key, merged, session_id=subject)
    return {entity.key: key, **merged, "created": not current}


def aggregate(
    port: RecordsPort,
    entity: EntityType,
    column: str,
    fn: Aggregate,
    where: Mapping[str, object],
    subject: str | None,
) -> dict[str, object]:
    rows = read(port, entity, where, subject)
    values = [float(v) for row in rows if isinstance(v := row.get(column), int | float)]
    return {"value": AGGREGATES[fn](values if fn != "count" else [1.0] * len(rows)), "rows": len(rows)}
