"""APIs de terceros (pendientes F3): la declaración, la tool generada y la primitiva `api.call`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tools import ApiSpec, ApiToolSpec, ToolCall, ToolCatalog, ToolContext, ToolError, ToolRunner, api_tool
from tools.apis import parse_parameters

MINDICADOR = ApiSpec.model_validate(
    {"base_url": "https://mindicador.cl/api", "operations": {"indicador": {"path": "/{codigo}"}}}
)
VALOR = ApiToolSpec(
    name="valor_indicador",
    description="Valor de hoy de un indicador económico.",
    api="mindicador",
    operation="indicador",
    parameters={"type": "object", "properties": {"codigo": {"type": "string"}}, "required": ["codigo"]},
)


class FakeApis:
    def __init__(self, answer: object = None, error: Exception | None = None) -> None:
        self.answer, self.error = answer, error
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def call(self, api: str, operation: str, params: dict[str, object], body: object) -> object:
        self.calls.append((api, operation, params))
        if self.error is not None:
            raise self.error
        return self.answer


def run(port: FakeApis, arguments: dict[str, object]) -> dict[str, object]:
    runner = ToolRunner(ToolCatalog([api_tool(VALOR, MINDICADOR)]))
    context = ToolContext(session_id="s-1", turn_id="t-1", ports={"apis": port})
    return runner.run(
        ToolCall(call_id="c-1", name="valor_indicador", arguments=arguments), context
    ).for_model()


def test_la_tool_declarada_llama_la_operacion_con_sus_argumentos() -> None:
    port = FakeApis({"serie": [{"valor": 38000.5}]})

    outcome = run(port, {"codigo": "uf"})

    assert outcome["status"] == "ok"
    assert outcome["result"] == {"serie": [{"valor": 38000.5}]}
    assert port.calls == [("mindicador", "indicador", {"codigo": "uf"})]


def test_un_get_es_una_tool_de_lectura_y_sus_args_salen_del_esquema() -> None:
    tool = api_tool(VALOR, MINDICADOR)

    assert type(tool).kind == "read"
    assert list(type(tool).Args.model_fields) == ["codigo"]
    assert run(FakeApis(), {})["status"] == "rejected"  # falta el requerido


def test_los_errores_del_puerto_llegan_tipados_al_modelo() -> None:
    outcome = run(
        FakeApis(error=ToolError("provider", "El servicio no responde.", retryable=True)), {"codigo": "uf"}
    )

    assert (outcome["error"], outcome["retryable"]) == ("provider", True)


def test_la_llamada_queda_en_la_auditoria_sin_cuerpos() -> None:
    from tools import Primitives

    p = Primitives(ToolContext(session_id="s", turn_id="t", ports={"apis": FakeApis({"x": 1})}))

    p.api.call("mindicador", "indicador", {"codigo": "uf"})

    assert [(c.primitive, c.target, c.status) for c in p.calls] == [
        ("api.call", "mindicador.indicador", "ok")
    ]


@pytest.mark.parametrize(
    ("spec", "problem"),
    [
        (VALOR.model_copy(update={"operation": "otra"}), "no tiene la operación 'otra'"),
        (VALOR.model_copy(update={"parameters": {}}), "necesita parámetros \\['codigo'\\]"),
    ],
)
def test_una_tool_que_no_calza_con_su_api_no_arranca(spec: ApiToolSpec, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        api_tool(spec, MINDICADOR)


def test_la_declaracion_de_la_api_se_valida() -> None:
    with pytest.raises(ValidationError, match="env"):
        ApiSpec.model_validate(
            {"base_url": "https://x", "auth": {"scheme": "bearer"}, "operations": {"a": {"path": "/"}}}
        )
    with pytest.raises(ValidationError):
        ApiSpec.model_validate({"base_url": "ftp://x", "operations": {"a": {"path": "/"}}})


def test_los_parametros_de_la_ficha_se_leen_con_o_sin_cerco() -> None:
    schema = '{"type": "object", "properties": {"a": {"type": "integer"}}}'
    raw = f'```json\n{{"name": "x", "parameters": {schema}}}\n```'

    assert parse_parameters(raw)["properties"] == {"a": {"type": "integer"}}
