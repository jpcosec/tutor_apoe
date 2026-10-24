"""Tipos de catálogo: modelos, relaciones, tipos de relación y conteos (spec 01 §7.1)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from kb.model.document import Document


class ModelInfo(BaseModel, frozen=True):
    name: str = Field(description="Nombre de la clase.")
    model_ref: str = Field(description="paquete.modulo:Clase.")
    base_models: list[str] = Field(description="Clases base registradas por sldb.")
    family: str | None = Field(description="__family__, si declara.")
    semantic_tags: list[str] = Field(description="Semántica del modelo, ordenada.")
    documents_count: int = Field(description="Conteo que registra core/models/<M>.yaml.")
    builtin: bool = Field(description="Modelo de sldb o pron, no de la KB.")


class RelationTypeInfo(BaseModel, frozen=True):
    name: str = Field(description="Nombre del tipo de relación.")
    direction: str = Field(description="directed | undirected")
    cardinality: str = Field(description="one_to_one | one_to_many | many_to_one | many_to_many")
    axis: str = Field(description="Eje semántico.")
    source_types: list[str] = Field(description="Modelos admitidos como origen.")
    target_types: list[str] = Field(description="Modelos admitidos como destino.")
    condition: str = Field(description="Condición declarada.")
    description: str = Field(description="Descripción.")
    builtin: bool = Field(description="Uno de los 11 tipos estructurales de sldb.")


class Relation(BaseModel, frozen=True):
    source_ref: str = Field(description="Modelo:nombre del origen.")
    target_ref: str = Field(description="Modelo:nombre del destino.")
    relation_type: str = Field(description="Tipo de relación.")
    condition: str = Field(default="", description="Condición de la arista.")
    doc: Document | None = Field(default=None, description="El RelationDoc; None en aristas estructurales.")


class KbStats(BaseModel, frozen=True):
    documents: int = Field(description="Documentos de contenido.")
    eligible: int = Field(description="Documentos elegibles.")
    by_model: dict[str, int] = Field(description="Por clase, incluidos los modelos con 0.")
    by_family: dict[str, int] = Field(description="Por __family__; '' para sin familia.")
    relations_by_type: dict[str, int] = Field(description="Solo tipos autorados.")
