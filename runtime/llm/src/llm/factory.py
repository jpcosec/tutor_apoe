"""De `LlmSettings` a un modelo del sustrato (spec 04 §7); ningún SDK de proveedor fuera de aquí."""

from __future__ import annotations

import asyncio
import os
import threading
import weakref
from collections.abc import Callable, Mapping
from typing import Any, cast

import boto3
import httpx2
from botocore.config import Config
from pydantic_ai.models import Model, infer_model
from pydantic_ai.models.bedrock import BedrockConverseModel
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.bedrock import BedrockProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.retries import AsyncHTTPX2TenacityTransport, RetryConfig, wait_retry_after
from pydantic_ai.settings import ModelSettings
from tenacity import retry_if_exception_type, stop_after_attempt, wait_exponential

from llm.capabilities import capabilities_of
from llm.conformance import check_report
from llm.settings import LlmSettings

OPENAI_COMPATIBLE = {"openai", "openrouter"}


#: Estados HTTP que se reintentan (04 §6.3): saturación, plazo y caídas del proveedor.
RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504})
MAX_WAIT_SECONDS = 30.0


def make_model(settings: LlmSettings, verify: bool = True) -> Model:
    """El modelo de Pydantic AI para el par, con los reintentos del transporte de cada proveedor
    y, si el cliente lo declara, un respaldo (`FallbackModel`) cuando el primero falla.

    Falla si el par no tiene capacidades declaradas; con `verify`, exige conformidad vigente en
    producción (I2).
    """
    primary = _checked(settings, verify)
    if settings.fallback is None:
        return primary
    return FallbackModel(primary, _checked(settings.fallback, verify))


def _checked(settings: LlmSettings, verify: bool) -> Model:
    capabilities_of(settings)
    if verify:
        check_report(settings, os.environ)
    return _substrate(settings)


def _substrate(settings: LlmSettings) -> Model:
    if settings.provider == "test":
        return infer_model("test")
    if settings.provider == "bedrock":
        return _bedrock(settings, os.environ)
    if settings.provider == "openrouter":
        return OpenAIChatModel(
            settings.model, provider=OpenRouterProvider(http_client=_http_client(settings))
        )
    if settings.provider in OPENAI_COMPATIBLE:
        provider = OpenAIProvider(base_url=settings.base_url, http_client=_http_client(settings))
        return OpenAIChatModel(settings.model, provider=provider)
    return infer_model(f"{settings.provider}:{settings.model}")


class LoopLocalTransport(httpx2.AsyncBaseTransport):
    """Un transporte por event loop: el pool de conexiones queda amarrado al loop que lo abrió.

    `Agent.run_sync` abre un loop por hilo; el motor corre turnos desde varios hilos (el pool de
    FastAPI, los webhooks, el worker). Compartir un pool entre loops falla con «bound to a
    different event loop» desde el segundo hilo.
    """

    def __init__(self, factory: Callable[[], httpx2.AsyncBaseTransport] = httpx2.AsyncHTTPTransport) -> None:
        self._factory = factory
        self._lock = threading.Lock()
        self._by_loop: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx2.AsyncBaseTransport] = (
            weakref.WeakKeyDictionary()
        )

    def current(self) -> httpx2.AsyncBaseTransport:
        loop = asyncio.get_running_loop()
        with self._lock:
            if loop not in self._by_loop:
                self._by_loop[loop] = self._factory()
            return self._by_loop[loop]

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        return await self.current().handle_async_request(request)

    async def aclose(self) -> None:
        with self._lock:
            transports, self._by_loop = list(self._by_loop.values()), weakref.WeakKeyDictionary()
        for transport in transports:
            await transport.aclose()


def _http_client(
    settings: LlmSettings, wrapped: httpx2.AsyncBaseTransport | None = None
) -> httpx2.AsyncClient:
    """Reintentos transitorios en el transporte (04 §6.2), con la librería de Pydantic AI:
    respeta `Retry-After` y, si no viene, espera exponencial con techo de 30 s."""

    def transient(response: httpx2.Response) -> None:
        if response.status_code in RETRY_STATUS:
            response.raise_for_status()

    config = RetryConfig(
        retry=retry_if_exception_type((httpx2.HTTPStatusError, httpx2.TransportError)),
        wait=wait_retry_after(
            fallback_strategy=wait_exponential(multiplier=1, max=MAX_WAIT_SECONDS), max_wait=MAX_WAIT_SECONDS
        ),
        stop=stop_after_attempt(settings.max_attempts),
        reraise=True,
    )
    inner = wrapped or LoopLocalTransport()
    transport = AsyncHTTPX2TenacityTransport(config=config, wrapped=inner, validate_response=transient)
    return httpx2.AsyncClient(transport=transport, timeout=settings.timeout_seconds)


def _bedrock(settings: LlmSettings, environ: Mapping[str, str]) -> Model:
    """Bedrock con el cliente de boto3 y sus reintentos adaptivos (04 §6.2).

    La clave de API de Bedrock va en `AWS_BEARER_TOKEN_BEDROCK` y botocore la usa como bearer;
    sin ella, las credenciales AWS. La región sale de `LlmSettings.region`, `AWS_REGION` o, por
    defecto, `us-east-1`.
    """
    region = settings.region or environ.get("AWS_REGION") or environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    config = Config(
        retries={"max_attempts": settings.max_attempts, "mode": "adaptive"},
        read_timeout=settings.timeout_seconds,
    )
    client = cast(Any, boto3.client("bedrock-runtime", region_name=region, config=config))  # pyright: ignore[reportUnknownMemberType]
    return BedrockConverseModel(settings.model, provider=BedrockProvider(bedrock_client=client))


def settings_from_env(settings: LlmSettings, environ: Mapping[str, str]) -> LlmSettings:
    """12 §4.2: `LLM_PROVIDER`, `LLM_MODEL` y `LLM_REGION` del descriptor ganan al `client.yaml`.

    `AWS_RUNTIME_REQUIRE_BEDROCK=1` (de dev) hace error de arranque cualquier otro proveedor.
    """
    overrides = {
        field: environ[name].strip()
        for field, name in (("provider", "LLM_PROVIDER"), ("model", "LLM_MODEL"), ("region", "LLM_REGION"))
        if environ.get(name, "").strip()
    }
    resolved = settings.model_copy(update=overrides)
    if environ.get("AWS_RUNTIME_REQUIRE_BEDROCK") == "1" and resolved.provider != "bedrock":
        raise ValueError(f"el despliegue exige Bedrock; el par es {resolved.pair}")
    return resolved


def model_settings(settings: LlmSettings) -> ModelSettings:
    """Timeout, temperatura y tope de salida para cada ejecución."""
    values: ModelSettings = {"timeout": settings.timeout_seconds}
    if settings.temperature is not None:
        values["temperature"] = settings.temperature
    if settings.max_output_tokens is not None:
        values["max_tokens"] = settings.max_output_tokens
    return values
