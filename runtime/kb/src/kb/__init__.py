"""Módulo 01: acceso de solo lectura a una KB sldb."""

from kb.declaration.manifest import load_manifest
from kb.declarations import SldbDeclarations
from kb.exceptions import (
    EmbedderMismatch,
    IndexNotDeclared,
    KnowledgeBaseError,
    KnowledgeBaseInvalid,
    KnowledgeBaseNotFound,
)
from kb.facade import KnowledgeBase
from kb.machines import (
    GraphCompileError,
    GraphCompiler,
    MachineGraph,
    collect_machine_graph,
)
from kb.model.catalog import KbStats, ModelInfo, Relation, RelationTypeInfo
from kb.model.document import Document, document_ref
from kb.payload import str_list
from kb.portable import StoreSources, TrackedSource, build_store, store_sources
from kb.rendering.materialize import strip_frontmatter
from kb.retracking import RetrackReport, retrack
from kb.retrieval import GOVERNANCE_TAGS, INDEX_DIR, Hit, IndexAudit, IndexReport, Projection
from kb.validation.report import ValidationError, ValidationReport
from kb.views import View, cell, contract_hash, render_view, table_view

__all__ = [
    "GOVERNANCE_TAGS",
    "INDEX_DIR",
    "Document",
    "EmbedderMismatch",
    "GraphCompileError",
    "GraphCompiler",
    "Hit",
    "IndexAudit",
    "IndexNotDeclared",
    "IndexReport",
    "KbStats",
    "KnowledgeBase",
    "KnowledgeBaseError",
    "KnowledgeBaseInvalid",
    "KnowledgeBaseNotFound",
    "MachineGraph",
    "ModelInfo",
    "Projection",
    "Relation",
    "RelationTypeInfo",
    "RetrackReport",
    "SldbDeclarations",
    "StoreSources",
    "TrackedSource",
    "ValidationError",
    "ValidationReport",
    "View",
    "build_store",
    "cell",
    "collect_machine_graph",
    "contract_hash",
    "document_ref",
    "load_manifest",
    "render_view",
    "retrack",
    "store_sources",
    "str_list",
    "strip_frontmatter",
    "table_view",
]
