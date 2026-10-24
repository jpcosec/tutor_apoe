"""`Document`: un documento de la KB tal como lo ven los consumidores (spec 01 §7.1)."""

from __future__ import annotations

from pydantic import Field

from ontology import OntologyObject, Ref


class Document(OntologyObject):
    schema_version: int = 1
    name: str = Field(description="Nombre sldb: archivo sin .md; identidad del documento (D5).")
    model: str = Field(description="Nombre de la clase del modelo.")
    model_ref: str = Field(description="paquete.modulo:Clase del modelo registrado.")
    ancestors: list[str] = Field(description="Clases ancestro, de la más cercana a la más lejana.")
    family: str | None = Field(description="__family__ del modelo, si declara.")
    model_tags: list[str] = Field(description="Tags que produce __semantics__ del modelo.")
    tags: list[str] = Field(description="Tags editoriales: campos tags y semantic_tags del payload.")
    all_tags: list[str] = Field(description="Unión de model_tags y tags.")
    path: str = Field(description="Ruta relativa a la raíz de la KB.")
    payload: dict[str, object] = Field(description="Campos extraídos por sldb, serializables a JSON.")
    eligible: bool = Field(description="Ningún tag bajo eligibility.blocked_tags (§4.4).")
    content_hash: str = Field(
        default="",
        description="Hash de los campos extraídos por sldb (su hash_d): cambia si cambia el contenido.",
    )

    @property
    def key(self) -> str:
        """`Modelo:nombre`, la forma corta con la que se refiere un documento."""
        return f"{self.model}:{self.name}"

    def is_a(self, model: str) -> bool:
        """Es de `model` o de una subclase suya (`{Modelo+}`, §3.4)."""
        return self.model == model or model in self.ancestors


def document_ref(model: str, name: str, release_id: str | None = None) -> Ref:
    """La `Ref` kb de un documento; nombre y modelo cumplen 13 §4.0 (lo garantiza V13 al abrir)."""
    return Ref(kind="kb", id=f"{model}:{name}", release_id=release_id)
