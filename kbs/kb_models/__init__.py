"""Esquema de la KB del tutor APOS (paquete `kb_models`, importable con pythonpath `kbs/`).

Lo que `kb` (runtime/kb) necesita de una KB sldb: modelos `StructuredNLDoc` con
`__family__`, `__semantics__` y `__template__`. Adaptado del esquema de referencia de
AntonIA (`kb_models.knowledge`) a lo mínimo que esta KB usa:

- `KnowledgeAtom` / `SourceAtom`: un átomo de conocimiento (pregunta 5WH1+, respuesta,
  procedencia, tags, padre en la taxonomía).
- `BranchNode`: un nodo de organización de la taxonomía (rama).
- `AgentDoc`: el rol del tutor (gobierno: ningún agente lo ve en su proyección).
- `TagNamespaceDoc`: una categoría de tags editoriales (`type.kb.category`).
- `SourceDoc` / `SourceChunk`: fuentes crudas ingeridas y sus fragmentos (`type.source.*`,
  familia `ingest`); fuera del índice y de la proyección del tutor.

La jerarquía padre→hijo no es un campo del grafo: son `RelationDoc` de tipo `child_of`
(el campo `parent` del átomo es solo la proyección legible de esa arista).
"""

from .apos import AtomQuestion, AtomTag, BranchNode, KnowledgeAtom, SourceAtom
from .governance import AgentDoc, StaticSection
from .ingest import SourceChunk, SourceDoc
from .kb_docs import TagNamespaceDoc

__all__ = [
    "AgentDoc",
    "AtomQuestion",
    "AtomTag",
    "BranchNode",
    "KnowledgeAtom",
    "SourceAtom",
    "SourceChunk",
    "SourceDoc",
    "StaticSection",
    "TagNamespaceDoc",
]
