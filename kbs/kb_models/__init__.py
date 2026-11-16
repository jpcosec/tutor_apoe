"""Esquema de la KB del tutor APOS (paquete `kb_models`, importable con pythonpath `kbs/`).

Lo que `kb` (runtime/kb) necesita de una KB sldb: modelos `StructuredNLDoc` con
`__family__`, `__semantics__` y `__template__`. Adaptado del esquema de referencia de
AntonIA (`kb_models.knowledge`) a lo mínimo que esta KB usa:

- `KnowledgeAtom` / `SourceAtom`: un átomo de conocimiento (pregunta 5WH1+, respuesta,
  procedencia estructurada `Provenance`, tags, padre en la taxonomía).
- `BranchNode`: un nodo de la taxonomía (rama) con descripción real y `Coverage` derivada.
- `AgentDoc`: el rol del tutor (gobierno: ningún agente lo ve en su proyección).
- `TagNamespaceDoc`: una categoría de tags editoriales (`type.kb.category`).
- `SourceDoc` / `SourceChunk` / `SourceOutline`: fuentes crudas ingeridas, sus fragmentos y
  su esquema capítulo→páginas→fragmentos (`type.source.*`, familia `ingest`); fuera del índice
  y de la proyección del tutor.
- `ProposedAtom`: un átomo propuesto por `tutor.compiler` (`type.proposal.atom`, familia
  `proposed`); fuera del índice y de la proyección hasta que se aprueba.

La jerarquía padre→hijo no es un campo del grafo: son `RelationDoc` de tipo `child_of`
(el campo `parent` del átomo es solo la proyección legible de esa arista).
"""

from .apos import AtomQuestion, AtomTag, BranchNode, KnowledgeAtom, SourceAtom, provenance_items
from .governance import AgentDoc, StaticSection
from .ingest import OutlineEntry, SourceChunk, SourceDoc, SourceOutline
from .kb_docs import TagNamespaceDoc
from .proposed import ProposalStatus, ProposedAtom
from .provenance import Coverage, Provenance, ProvenanceKind, parse_provenance_prose, render_coverage, render_provenance

__all__ = [
    "AgentDoc",
    "AtomQuestion",
    "AtomTag",
    "BranchNode",
    "Coverage",
    "KnowledgeAtom",
    "OutlineEntry",
    "ProposalStatus",
    "ProposedAtom",
    "Provenance",
    "ProvenanceKind",
    "SourceAtom",
    "SourceChunk",
    "SourceDoc",
    "SourceOutline",
    "StaticSection",
    "TagNamespaceDoc",
    "parse_provenance_prose",
    "provenance_items",
    "render_coverage",
    "render_provenance",
]
