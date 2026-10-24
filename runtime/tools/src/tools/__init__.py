"""Módulo 03: las tools de negocio. Su interfaz tiene tres audiencias; cada bloque de `__all__`
dice cuál es la suya."""

from tools.apis import ApiAuth, ApiOperation, ApiSpec, ApisPort, ApiTool, ApiToolSpec, api_tool
from tools.check_kb import check_kb
from tools.contract import (
    Conflict,
    ErrorClass,
    FieldError,
    IdentityCheck,
    IdentityRequirement,
    NotFound,
    ProviderError,
    Tool,
    ToolCall,
    ToolCallEpisode,
    ToolContext,
    ToolDeclaration,
    ToolError,
    ToolOutcome,
    ToolResult,
)
from tools.entity import EntityType, EpisodeSpec
from tools.event_tools import EventSpec, EventTool, event_tool
from tools.idempotency import IdempotencyPort
from tools.kb_operations import api_specs, event_specs, operation_specs
from tools.operation_tools import (
    BINDING_SOURCES,
    STATE_PREFIX,
    OperationConfigError,
    OperationSpec,
    OperationTool,
    operation_tool,
)
from tools.primitives import PrimitiveCall, Primitives, SemanticTool
from tools.runner import ToolCatalog, ToolRunner
from tools.tool_tests import Fixture, ToolTestCase, ToolTestResult, run_tool_test, tool_test_cases
from tools.toolset import business_toolset

# El runtime: el contrato de una tool, su catálogo y cómo se ejecuta (03 §6.1–§6.3).
__all__ = [
    "STATE_PREFIX",
    "ErrorClass",
    "FieldError",
    "IdempotencyPort",
    "IdentityCheck",
    "IdentityRequirement",
    "Tool",
    "ToolCall",
    "ToolCallEpisode",
    "ToolCatalog",
    "ToolContext",
    "ToolDeclaration",
    "ToolOutcome",
    "ToolResult",
    "ToolRunner",
    "business_toolset",
]
# Quien escribe las tools de un cliente o las declara en la KB (03 §6.4–§6.6, 14 §6.7).
__all__ += [
    "BINDING_SOURCES",
    "ApiAuth",
    "ApiOperation",
    "ApiSpec",
    "ApiTool",
    "ApiToolSpec",
    "ApisPort",
    "Conflict",
    "EntityType",
    "EpisodeSpec",
    "EventSpec",
    "EventTool",
    "NotFound",
    "OperationConfigError",
    "OperationSpec",
    "OperationTool",
    "PrimitiveCall",
    "Primitives",
    "ProviderError",
    "SemanticTool",
    "ToolError",
    "api_specs",
    "api_tool",
    "event_specs",
    "event_tool",
    "operation_specs",
    "operation_tool",
]
# Las pruebas de un cliente: los ToolTestDoc de la KB y el chequeo contra la KB (03 §8).
__all__ += [
    "Fixture",
    "ToolTestCase",
    "ToolTestResult",
    "check_kb",
    "run_tool_test",
    "tool_test_cases",
]
