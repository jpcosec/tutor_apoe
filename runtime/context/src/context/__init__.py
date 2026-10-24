"""Spec 14: el contexto del flujo agéntico, su ruteador por rol y su proyección determinista."""

from context.atoms import AtomEntry, LedgerEvent, replay_active
from context.episodes import AgentRun, StepVisit, agent_run, close_visits, move_to
from context.knowledge import (
    KnowledgeActivationsByVersion,
    KnowledgeError,
    KnowledgeLifecycle,
    KnowledgeProjection,
)
from context.model import Context
from context.projection import Projection, project
from context.router import Candidate, ContextRouter, RoleRoute, RouteContextConfig, tool_name
from context.selector import ContextSelection, LlmSelector, Selector
from context.store import ContextStore, InMemoryContextStore, load, save
from context.substrates import (
    ContextProjector,
    EvidenceError,
    EvidenceSelection,
    ExecutionProcesses,
    KbSelfDeclarations,
    SelfDeclarations,
    SnapshotBuilder,
)
from context.summary import TurnSummary

__all__ = [
    "AgentRun",
    "AtomEntry",
    "Candidate",
    "Context",
    "ContextProjector",
    "ContextRouter",
    "ContextSelection",
    "ContextStore",
    "EvidenceError",
    "EvidenceSelection",
    "ExecutionProcesses",
    "InMemoryContextStore",
    "KbSelfDeclarations",
    "KnowledgeActivationsByVersion",
    "KnowledgeError",
    "KnowledgeLifecycle",
    "KnowledgeProjection",
    "LedgerEvent",
    "LlmSelector",
    "Projection",
    "RoleRoute",
    "RouteContextConfig",
    "Selector",
    "SelfDeclarations",
    "SnapshotBuilder",
    "StepVisit",
    "TurnSummary",
    "agent_run",
    "close_visits",
    "load",
    "move_to",
    "project",
    "replay_active",
    "save",
    "tool_name",
]
