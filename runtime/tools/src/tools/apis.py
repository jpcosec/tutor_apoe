"""APIs de terceros como primitiva (03 §4.5, pendientes F3): declaración, puerto y tool declarada.

Una API se declara en `client.yaml` (`apis:`) con su URL, su autenticación (el nombre de la
variable de entorno con el secreto, nunca el valor) y una **lista cerrada de operaciones**. Las
tools la usan por `p.api.call(api, operación, params)`; el adaptador HTTP lo pone el ensamblaje
en el puerto `apis`. Una tool de la KB (`ExternalApiToolAtom`) cuyo `provider` es una API
declarada y cuyo `endpoint` es una de sus operaciones se vuelve tool sin código (`api_tool`).
"""

from __future__ import annotations

import json
import re
import string
from typing import Any, ClassVar, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from tools.contract import Tool, ToolResult
from tools.primitives import Primitives, SemanticTool

JSON_TYPES: dict[str, type] = {"string": str, "integer": int, "number": float, "boolean": bool}


class ApiAuth(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")
    scheme: Literal["none", "header", "bearer"] = "none"
    header: str | None = Field(default=None, description="Cabecera con la clave (scheme: header).")
    env: str | None = Field(default=None, description="Variable de entorno con el secreto.")

    @model_validator(mode="after")
    def _complete(self) -> ApiAuth:
        if self.scheme != "none" and not self.env:
            raise ValueError("una API con autenticación necesita `env` (la variable con el secreto)")
        if self.scheme == "header" and not self.header:
            raise ValueError("scheme: header necesita el nombre de la cabecera")
        return self


class ApiOperation(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")
    method: Literal["GET", "POST"] = "GET"
    path: str = Field(description="Ruta bajo base_url; `{param}` se llena con los parámetros.")

    @property
    def placeholders(self) -> list[str]:
        return [field for _, field, _, _ in string.Formatter().parse(self.path) if field]


class ApiSpec(BaseModel, frozen=True):
    """Una API de `client.yaml`: nada fuera de sus operaciones se puede llamar."""

    model_config = ConfigDict(extra="forbid")
    base_url: str = Field(pattern=r"^https?://")
    auth: ApiAuth = Field(default_factory=ApiAuth)
    timeout_seconds: float = Field(default=10.0, gt=0)
    max_attempts: int = Field(default=2, ge=1, description="Solo las lecturas (GET) se reintentan.")
    max_bytes: int = Field(default=500_000, gt=0, description="Respuesta más grande: error del proveedor.")
    operations: dict[str, ApiOperation] = Field(min_length=1)


class ApisPort(Protocol):
    """El adaptador HTTP (lo pone el ensamblaje): valida contra la declaración y tipa los errores."""

    def call(
        self, api: str, operation: str, params: dict[str, object], body: dict[str, object] | None
    ) -> object: ...


class ApiToolSpec(BaseModel, frozen=True):
    """Una tool de la KB sobre una operación de una API declarada."""

    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    api: str
    operation: str
    parameters: dict[str, Any] = Field(default_factory=dict[str, Any], description="JSON Schema de los args.")


class ApiTool(SemanticTool):
    spec: ClassVar[ApiToolSpec]

    def run(self, p: Primitives, args: BaseModel) -> ToolResult:
        params = args.model_dump(exclude_none=True)
        return ToolResult(data={"result": p.api.call(self.spec.api, self.spec.operation, params)})


def api_tool(spec: ApiToolSpec, api: ApiSpec) -> Tool:
    """La `Tool` para una declaración; una operación que la API no tiene es error de arranque."""
    operation = api.operations.get(spec.operation)
    if operation is None:
        raise ValueError(f"{spec.name}: la API {spec.api!r} no tiene la operación {spec.operation!r}")
    args = _args(spec)
    missing = sorted(set(operation.placeholders) - set(args.model_fields))
    if missing:
        raise ValueError(f"{spec.name}: la ruta {operation.path!r} necesita parámetros {missing}")
    attributes: dict[str, Any] = {
        "name": spec.name,
        "description": spec.description,
        "Args": args,
        "kind": "read" if operation.method == "GET" else "external",
        "spec": spec,
    }
    return type(f"ApiTool_{spec.name}", (ApiTool,), attributes)()


def parse_parameters(raw: object) -> dict[str, Any]:
    """El `## Parameters` de una ficha de tool (`{"name", "parameters": {…}}`, con o sin cerco
    de código) como JSON Schema de los argumentos."""
    if isinstance(raw, str):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
        raw = json.loads(text) if text else {}
    if not isinstance(raw, dict):
        return {}
    spec: dict[str, Any] = raw  # pyright: ignore[reportUnknownVariableType]
    params = spec.get("parameters", spec)
    return params if isinstance(params, dict) else {}  # pyright: ignore[reportUnknownVariableType]


def _args(spec: ApiToolSpec) -> type[BaseModel]:
    properties: dict[str, Any] = spec.parameters.get("properties") or {}
    required = set(spec.parameters.get("required") or [])
    fields: dict[str, Any] = {}
    for name, schema in properties.items():
        kind = JSON_TYPES.get(str(schema.get("type", "string")), str)
        description = str(schema.get("description") or "")
        if name in required:
            fields[name] = (kind, Field(description=description))
        else:
            fields[name] = (kind | None, Field(default=None, description=description))
    return create_model(f"{spec.name}_args", __config__=ConfigDict(extra="forbid"), **fields)
