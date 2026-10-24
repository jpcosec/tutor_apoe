"""Vistas: modelos con plantilla sldb para renderizar objetos del runtime (spec 15 §3, §6.1).

Una vista no tiene documentos ni store: es un contrato (campos y plantilla) y un render.
01 sigue siendo el único que habla con sldb; `semantics` crea y renderiza vistas por aquí.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field, create_model
from sldb import StructuredNLDoc

from kb.loading import sldb_gateway as sldb

View = type[StructuredNLDoc]


def table_view(name: str, columns: dict[str, str], heading: str = "") -> View:
    """Una tabla de filas con encabezado opcional (`#### …`); `columns` es columna → descripción."""
    fields: dict[str, Any] = {column: (str, Field(description=text)) for column, text in columns.items()}
    row = create_model(f"{name}Row", **fields)
    table = f"⸢rev,table[{','.join(columns)}]•rows⸥"
    template = f"{heading}\n\n{table}" if heading else table
    attributes: dict[str, Any] = {
        "__template__": template,
        "__annotations__": {"rows": list[row]},  # pyright: ignore[reportInvalidTypeForm]
        "rows": Field(default_factory=list, description="Filas de la tabla."),
        "__module__": __name__,
    }
    return type(name, (StructuredNLDoc,), attributes)


def render_view(view: View, rows: list[dict[str, str]]) -> str:
    return sldb.render(view, {"rows": rows}).strip()


def contract_hash(view: View) -> str:
    """Plantilla más esquema de campos: lo que define cómo se ve la vista (15 O3)."""
    schema = view.model_json_schema()
    contract = json.dumps(
        {"template": view.__template__, "schema": schema}, sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(contract.encode()).hexdigest()


def cell(value: object) -> str:
    """El texto de una celda: los anidados como JSON, nunca repr de Python; nulo, vacío (15 §6.1)."""
    if value is None:
        return ""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, dict | list | tuple):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value).replace("|", "\\|").replace("\n", " ")
