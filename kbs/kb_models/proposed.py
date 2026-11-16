"""Átomos propuestos por el compilador (`tutor.compiler`), pendientes de revisión humana.

Un `ProposedAtom` tiene la misma forma que un `KnowledgeAtom` (pregunta, respuesta, procedencia,
tags, padre) más lo que hace falta para juzgarlo: qué se pidió (`request`), qué modelo lo propuso
(`created_by`), por qué (`rationale`), a qué átomos existentes se parece (`similar_to`), si Jev
lo vio respaldado por el fragmento citado (`grounded`) y su `status`.

NO es subclase de `KnowledgeAtom` a propósito: `projection-tutor` nombra `KnowledgeAtom` y
`BranchNode` (con subclases) y `kb.yaml` indexa solo `KnowledgeAtom`, así que un propuesto no entra
ni a la mesa del tutor ni al índice hasta que `approve` lo reescribe como `KnowledgeAtom` con el
mismo id. Tampoco lleva arista `child_of`: `parent` es solo el destino que tendrá al aprobarse.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field
from sldb import StructuredNLDoc

from .apos import AtomQuestion, AtomTag


class ProposalStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class ProposedAtom(StructuredNLDoc):
    """Un átomo candidato: lo que el compilador propone y una persona aprueba o rechaza."""

    __family__ = "proposed"
    __semantics__ = {"type": ["proposal", "atom"], "workspace": ["ingest"]}
    __template__ = """---
id: ⸢rev•id⸥
title: ⸢rev•title⸥
five_wh_one_plus: ⸢rev•five_wh_one_plus⸥
tags: ⸢rev•tags⸥
parent: ⸢rev•parent⸥
status: ⸢rev•status⸥
request: ⸢rev•request⸥
created_by: ⸢rev•created_by⸥
chunk_ids: ⸢rev•chunk_ids⸥
similar_to: ⸢rev•similar_to⸥
grounded: ⸢optrev•grounded⸥
rejected_why: ⸢optrev•rejected_why⸥
---

# ⸢render•title⸥

## Respuesta

⸢rev•answer⸥

## Procedencia

⸢rev•provenance⸥

## Justificación

⸢rev•rationale⸥
""".strip()

    id: str = Field(description="Identificador estable, igual al nombre del documento; 'atom-<slug>' (el que tendrá al aprobarse).")
    title: str = Field(description="Título corto: la afirmación en una frase.")
    five_wh_one_plus: AtomQuestion = Field(description="La única pregunta 5WH1+ que responde.")
    tags: list[AtomTag] = Field(default_factory=list, description="Tags editoriales (system:, topic:, layer:, domain:).")
    parent: str = Field(description="BranchNode del que colgará al aprobarse.")
    status: ProposalStatus = Field(default=ProposalStatus.PROPOSED, description="proposed | approved | rejected.")
    request: str = Field(description="Qué se le pidió al compilador (tema o pregunta de estudiante).")
    created_by: str = Field(description="Modelo que lo propuso (provider:model).")
    chunk_ids: list[str] = Field(default_factory=list, description="SourceChunk que respaldan la respuesta.")
    similar_to: list[str] = Field(default_factory=list, description="Átomos existentes parecidos (id:score).")
    grounded: bool | None = Field(default=None, description="Si Jev juzgó la respuesta respaldada por el fragmento citado; None si no se evaluó.")
    rejected_why: str | None = Field(default=None, description="Motivo del rechazo, si lo hubo.")
    answer: str = Field(description="La respuesta propuesta: una sola afirmación, ≤ 80 palabras.")
    provenance: str = Field(description="chunk_ids + cita textual corta + página/sección.")
    rationale: str = Field(description="Por qué el compilador cree que este átomo hace falta.")
