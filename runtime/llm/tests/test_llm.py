from __future__ import annotations

from typing import Any, cast

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models.fallback import FallbackModel

from llm import (
    InternalFault,
    LlmAuthError,
    LlmError,
    LlmInvalidRequest,
    LlmOutputInvalid,
    LlmRateLimited,
    LlmRejected,
    LlmSettings,
    LlmTimeout,
    LlmTransient,
    LlmUnavailable,
    LlmUnexpected,
    LlmUnknownModel,
    LlmUsageLimit,
    ScriptedModel,
    ScriptedStep,
    capabilities_of,
    classify,
    make_model,
    model_settings,
    settings_from_env,
)


def test_capacidades_por_par_y_por_proveedor() -> None:
    assert capabilities_of(LlmSettings(provider="openrouter", model="x")).tools is True
    with pytest.raises(LlmUnknownModel):
        capabilities_of(LlmSettings(provider="nadie", model="x"))


def test_make_model_y_ajustes() -> None:
    settings = LlmSettings(provider="test", model="x", temperature=0.2, max_output_tokens=50)

    assert make_model(settings).model_name == "test"
    assert model_settings(settings) == {"timeout": 30.0, "temperature": 0.2, "max_tokens": 50}
    with pytest.raises(LlmUnknownModel):
        make_model(LlmSettings(provider="nadie", model="x"))


def test_scripted_texto_y_estructurado() -> None:
    class Out(BaseModel):
        answer: str

    scripted = ScriptedModel([ScriptedStep(text="hola"), ScriptedStep(text="", structured={"answer": "sí"})])

    text = Agent(scripted.model, instructions="sé breve").run_sync("hola")
    typed = Agent(scripted.model, output_type=Out).run_sync("¿sí?")

    assert text.output == "hola"
    assert typed.output == Out(answer="sí")
    assert scripted.instructions[0] == "sé breve"
    with pytest.raises(AssertionError, match="fuera de guion"):
        Agent(scripted.model).run_sync("otra")


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (type("E", (Exception,), {"status_code": 429})(), LlmRateLimited),
        (type("E", (Exception,), {"status_code": 503})(), LlmUnavailable),
        (type("E", (Exception,), {"status_code": 408})(), LlmUnavailable),
        (type("E", (Exception,), {"status_code": 401})(), LlmAuthError),
        (type("E", (Exception,), {"status_code": 422})(), LlmInvalidRequest),
        (type("E", (Exception,), {"status_code": 404})(), LlmRejected),
        (TimeoutError("t"), LlmTimeout),
        (ConnectionError("c"), LlmUnavailable),
        (UsageLimitExceeded("tope"), LlmUsageLimit),
        (UnexpectedModelBehavior("Exceeded maximum retries (1) for output validation"), LlmOutputInvalid),
        (UnexpectedModelBehavior("raro"), LlmUnexpected),
        (ValueError("x"), InternalFault),
    ],
)
def test_clasificacion(exc: Exception, expected: type[LlmError]) -> None:
    error = classify(exc)

    assert type(error) is expected
    assert isinstance(error, LlmTransient) == (expected in (LlmRateLimited, LlmUnavailable, LlmTimeout))


def test_region_de_bedrock_y_base_url_fijan_el_proveedor() -> None:
    from pydantic_ai.models.bedrock import BedrockConverseModel
    from pydantic_ai.models.openai import OpenAIChatModel

    bedrock = make_model(
        LlmSettings(provider="bedrock", model="us.anthropic.claude-haiku", region="us-east-1")
    )
    local = make_model(LlmSettings(provider="openai", model="qwen", base_url="http://localhost:8080/v1"))

    assert isinstance(bedrock, BedrockConverseModel)
    assert isinstance(local, OpenAIChatModel)
    assert local.base_url.startswith("http://localhost:8080")


def test_el_descriptor_gana_al_client_yaml_y_bedrock_obligatorio() -> None:
    base = LlmSettings(provider="openrouter", model="nemotron")

    resolved = settings_from_env(
        base, {"LLM_PROVIDER": "bedrock", "LLM_MODEL": "claude", "LLM_REGION": "us-east-1"}
    )

    assert (resolved.provider, resolved.model, resolved.region) == ("bedrock", "claude", "us-east-1")
    assert settings_from_env(base, {}) == base
    with pytest.raises(ValueError, match="Bedrock"):
        settings_from_env(base, {"AWS_RUNTIME_REQUIRE_BEDROCK": "1"})


def test_bedrock_con_clave_de_api_usa_bearer_y_region_por_defecto(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic_ai.models.bedrock import BedrockConverseModel

    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "clave-de-prueba")
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    model = make_model(LlmSettings(provider="bedrock", model="us.anthropic.claude-haiku-4-5-20251001-v1:0"))
    assert isinstance(model, BedrockConverseModel)
    client = cast(Any, model).client
    seen: dict[str, object] = {}

    def capture(request: Any, **_: object) -> None:
        seen["auth"] = request.headers.get("Authorization")
        raise RuntimeError("interceptado")

    client.meta.events.register("before-send", capture)
    with pytest.raises(RuntimeError, match="interceptado"):
        client.converse(modelId="x", messages=[{"role": "user", "content": [{"text": "hola"}]}])

    assert client.meta.region_name == "us-east-1"
    assert client.meta.config.retries["mode"] == "adaptive"  # reintentos de botocore (04 §6.2)
    assert seen["auth"] == b"Bearer clave-de-prueba"  # botocore usa la clave de API como bearer


def test_con_respaldo_declarado_el_modelo_es_un_fallback() -> None:
    settings = LlmSettings(provider="test", model="x", fallback=LlmSettings(provider="test", model="y"))

    assert isinstance(make_model(settings), FallbackModel)
    assert not isinstance(make_model(settings.model_copy(update={"fallback": None})), FallbackModel)


def test_el_transporte_reintenta_lo_transitorio_y_no_un_rechazo() -> None:
    """04 §6.2 con la librería: 503 y 429 se reintentan (respetando `Retry-After`); 400 no."""
    import asyncio

    import httpx2

    from llm.factory import _http_client  # pyright: ignore[reportPrivateUsage]

    def served(*statuses: int) -> tuple[httpx2.MockTransport, list[int]]:
        calls: list[int] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            calls.append(1)
            status = statuses[min(len(calls), len(statuses)) - 1]
            return httpx2.Response(status, headers={"Retry-After": "0"}, json={})

        return httpx2.MockTransport(handler), calls

    settings = LlmSettings(provider="openrouter", model="x", max_attempts=3)
    flaky, flaky_calls = served(503, 429, 200)
    bad, bad_calls = served(400)

    async def get(transport: httpx2.MockTransport) -> int:
        async with _http_client(settings, transport) as client:
            return (await client.get("https://llm.test/v1")).status_code

    assert (asyncio.run(get(flaky)), len(flaky_calls)) == (200, 3)
    assert (asyncio.run(get(bad)), len(bad_calls)) == (400, 1)


def test_el_mismo_cliente_sirve_desde_varios_hilos() -> None:
    """`run_sync` abre un loop por hilo: el pool de conexiones no puede quedar amarrado al primero."""
    import asyncio
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from llm.factory import _http_client  # pyright: ignore[reportPrivateUsage]

    class Ok(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Ok)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = _http_client(LlmSettings(provider="openrouter", model="x", max_attempts=1))
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    statuses: list[int | str] = []

    def call() -> None:
        loop = asyncio.new_event_loop()  # como `run_sync`: un loop por hilo, que queda abierto
        try:
            statuses.append(loop.run_until_complete(client.get(url)).status_code)
        except Exception as error:
            statuses.append(repr(error))

    for _ in range(3):
        worker = threading.Thread(target=call)
        worker.start()
        worker.join()
    server.shutdown()

    assert statuses == [200, 200, 200]
