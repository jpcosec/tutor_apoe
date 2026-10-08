"""Operaciones de bajo nivel y tools de alto nivel con `bind` (spec 14 §6.7, C6 y C7)."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from data import SqlStore
from tools import (
    EntityType,
    OperationConfigError,
    OperationSpec,
    Primitives,
    SemanticTool,
    ToolCall,
    ToolCatalog,
    ToolContext,
    ToolResult,
    ToolRunner,
    operation_tool,
)
from tools.operations import aggregate, read, write

FACTURA = EntityType.declare(
    "factura", key="folio", fields={"monto": "integer", "estado": "string", "vencimiento": "string"}
)
DETALLE = OperationSpec(
    name="detalle_factura",
    description="Facturas de la persona.",
    operation="read",
    entity="factura",
    inputs=["folio"],
    bind={"subject": "context.subject"},
)


@pytest.fixture
def store() -> SqlStore:
    store = SqlStore("sqlite://")
    store.put_record("factura", "1042", {"monto": 350000, "estado": "pendiente"}, session_id="ana")
    store.put_record("factura", "1043", {"monto": 50000, "estado": "pendiente"}, session_id="ana")
    store.put_record("factura", "2001", {"monto": 99, "estado": "pendiente"}, session_id="otra")
    return store


def run(
    store: SqlStore, spec: OperationSpec, arguments: dict[str, object], subject: str = "ana"
) -> dict[str, object]:
    runner = ToolRunner(ToolCatalog([operation_tool(spec, FACTURA)]))
    context = ToolContext(
        session_id=subject, turn_id="t-1", ports={"records": store}, bindings={"context.subject": subject}
    )
    return runner.run(ToolCall(call_id="c-1", name=spec.name, arguments=arguments), context).for_model()


@pytest.mark.spec("14-C7")
def test_read_devuelve_todas_las_filas_del_sujeto_y_nunca_elige(store: SqlStore) -> None:
    rows = read(store, FACTURA, {"estado": "pendiente"}, "ana")

    assert [r["folio"] for r in rows] == ["1042", "1043"]


@pytest.mark.spec("14-C6")
def test_el_sujeto_lo_pone_el_contexto_y_la_llm_no_lo_ve(store: SqlStore) -> None:
    tool = operation_tool(DETALLE, FACTURA)

    schema = type(tool).declaration().parameters
    result = run(store, DETALLE, {})

    assert set(schema["properties"]) == {"folio"}  # pyright: ignore[reportArgumentType]
    assert schema.get("required") in (None, [])
    assert result["count"] == 2
    assert run(store, DETALLE, {"folio": "2001"})["count"] == 0  # de otra persona: no aparece


def test_la_llm_no_puede_pasar_el_sujeto(store: SqlStore) -> None:
    result = run(store, DETALLE, {"subject": "otra"})

    assert result["status"] == "rejected"


def test_write_crea_y_actualiza_sin_pisar(store: SqlStore) -> None:
    created = write(store, FACTURA, "1044", {"monto": 10}, "ana")
    updated = write(store, FACTURA, "1044", {"estado": "pagada"}, "ana")

    assert (created["created"], updated["created"]) == (True, False)
    assert updated["monto"] == 10


def test_aggregate_sobre_una_columna(store: SqlStore) -> None:
    assert aggregate(store, FACTURA, "monto", "sum", {}, "ana") == {"value": 400000.0, "rows": 2}
    assert aggregate(store, FACTURA, "monto", "count", {}, "ana") == {"value": 2, "rows": 2}


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"bind": {}}, "falta bind subject"),
        ({"inputs": ["inventado"]}, "no tiene 'inventado'"),
        ({"bind": {"subject": "context.subject", "folio": "context.session"}}, "no puede venir de la LLM"),
        ({"bind": {"subject": "headers.x"}}, "no admitida"),
        ({"operation": "aggregate"}, "aggregate necesita"),
        ({"operation": "write", "inputs": ["monto"]}, "write necesita la clave"),
    ],
)
def test_declaracion_invalida_es_error_de_arranque(change: dict[str, object], problem: str) -> None:
    with pytest.raises(OperationConfigError, match=problem):
        operation_tool(DETALLE.model_copy(update=change), FACTURA)


CONTACTO = EntityType.declare(
    "contacto",
    key="rut",
    fields={"whatsapp": "string", "segmento": "string"},
    personal_fields=frozenset({"rut", "whatsapp"}),
)
POR_WHATSAPP = OperationSpec(
    name="contacto_por_whatsapp",
    description="Busca un contacto.",
    operation="read",
    entity="contacto",
    inputs=["whatsapp"],
    bind={"subject": "context.subject"},
)


def test_una_tool_que_filtra_por_un_campo_personal_no_arranca() -> None:
    with pytest.raises(OperationConfigError, match="campo personal 'whatsapp'"):
        operation_tool(POR_WHATSAPP, CONTACTO)
    operation_tool(POR_WHATSAPP.model_copy(update={"inputs": ["rut", "segmento"]}), CONTACTO)  # la clave sí


def test_leer_por_un_campo_personal_es_un_defecto_de_la_tool(store: SqlStore) -> None:
    from tools import ToolError

    with pytest.raises(ToolError, match="defect"):
        read(store, CONTACTO, {"whatsapp": "+56912345678"}, None)


class _NoArgs(BaseModel):
    pass


class _MarkPaid(SemanticTool):
    """Escribe una factura; `writes` lo cambia cada prueba."""

    name = "marcar_pagada"
    description = "Marca la factura 1042 como pagada."
    Args = _NoArgs

    def run(self, p: Primitives, args: BaseModel) -> ToolResult:
        return ToolResult(data={"row": p.records.write(FACTURA, "1042", {"estado": "pagada"}, "ana")})


@pytest.mark.parametrize(("writes", "status"), [(("factura",), "ok"), ((), "error")])
def test_una_tool_solo_escribe_lo_que_declara(store: SqlStore, writes: tuple[str, ...], status: str) -> None:
    tool = type("MarkPaid", (_MarkPaid,), {"writes": writes})()
    runner = ToolRunner(ToolCatalog([tool]))
    context = ToolContext(session_id="ana", turn_id="t-1", ports={"records": store})

    outcome = runner.run(ToolCall(call_id="c-1", name="marcar_pagada"), context)

    assert outcome.status == status
    assert outcome.error_class == (None if status == "ok" else "forbidden")
    stored = store.get_record("factura", "1042")
    assert stored is not None
    assert stored.fields["estado"] == ("pagada" if status == "ok" else "pendiente")
