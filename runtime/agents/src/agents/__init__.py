"""Módulo 05: agentes declarados, instrucciones compiladas desde la KB, ejecución sobre Pydantic AI.
Su interfaz tiene tres audiencias; cada bloque de `__all__` dice cuál es la suya."""

from agents.compile import CompiledAgent, GovernanceVisible, InstructionVariant, compile_agent, compile_all
from agents.declaration import AgentDecl, AgentsDeclaration, ContextDecl, StaticSection, load_agents
from agents.kb_tools import KB_TOOLS, KbReader
from agents.prompt import DYNAMIC_FIELDS, Instructions, instructions_for, render_context
from agents.providers import body_of
from agents.run import AgentOutput, AgentRunner, DecisionOutput, HistoryMessage, ReviewOutput, RunUsageView
from agents.schemas import (
    SCHEMAS,
    WITH_CLAIMS,
    Claim,
    DraftWithEvidence,
    GateVerdict,
    ToolCallRequest,
    TurnDecision,
    Violation,
)
from agents.segments import Profile, applies, holds

# El ensamblaje y el release: declarar y compilar los agentes desde la KB (05 §4, §6.7).
__all__ = [
    "AgentDecl",
    "AgentsDeclaration",
    "CompiledAgent",
    "ContextDecl",
    "GovernanceVisible",
    "InstructionVariant",
    "StaticSection",
    "compile_agent",
    "compile_all",
    "load_agents",
]
# El turno: correr un agente y leer su salida (05 §6.1–§6.6).
__all__ += [
    "DYNAMIC_FIELDS",
    "KB_TOOLS",
    "AgentOutput",
    "AgentRunner",
    "DecisionOutput",
    "HistoryMessage",
    "Instructions",
    "KbReader",
    "Profile",
    "ReviewOutput",
    "RunUsageView",
    "applies",
    "body_of",
    "holds",
    "instructions_for",
    "render_context",
]
# Los esquemas de salida versionados (05 §6.4).
__all__ += [
    "SCHEMAS",
    "WITH_CLAIMS",
    "Claim",
    "DraftWithEvidence",
    "GateVerdict",
    "ToolCallRequest",
    "TurnDecision",
    "Violation",
]
