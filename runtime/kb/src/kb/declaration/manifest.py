"""`kb.yaml`: el contrato `kb_version: 1` (spec 01 §4.1)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from kb.exceptions import KnowledgeBaseNotFound
from kb.validation.report import ValidationError

MANIFEST = "kb.yaml"
DEFAULT_BLOCKED_TAGS = [
    "status:proposed",
    "status:deprecated",
    "status:inactive",
    "status:placeholder-pending-mlr",
]


class Eligibility(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")
    blocked_tags: list[str] = Field(default_factory=lambda: list(DEFAULT_BLOCKED_TAGS), description="§4.4")


class Materialize(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")
    order: list[str] = Field(default_factory=list[str], description="Orden de grupos por __family__ (§6.2).")


class IndexPolicy(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")
    models: list[str] = Field(default_factory=list[str], description="Modelos del corpus; vacío = elegibles.")
    text: str = Field(default="summary", description="summary | fields:<campo,campo>")
    text_id: str = Field(default="summary", description="Nombre de esa lectura.")
    embedder_id: str = Field(description="Embedder del índice.")


class KbManifest(BaseModel, frozen=True):
    """La declaración de la KB; claves desconocidas bajo `kb:` son V0."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", description="Nombre de la KB.")
    kb_version: Literal[1] = Field(description="Versión del contrato.")
    models: str = Field(description="Paquete Python con los modelos.")
    pythonpath: str = Field(default=".", description="Relativo a kb.yaml.")
    eligibility: Eligibility = Field(default_factory=Eligibility, description="§4.4")
    materialize: Materialize = Field(default_factory=Materialize, description="§6.2")
    categories: Literal["required", "optional"] = Field(default="optional", description="§4.3")
    index: IndexPolicy | None = Field(default=None, description="§6.3")
    template: object = Field(default=None, description="Reservado al tooling del repo de KBs.")
    listen: object = Field(default=None, description="Reservado (pron serve).")
    prefixes: object = Field(default=None, description="Reservado (track por prefijo).")

    def resolved_pythonpath(self, root: Path) -> Path:
        return (root / self.pythonpath).resolve()


def load_manifest(root: Path) -> tuple[KbManifest | None, list[ValidationError]]:
    """Lee `<root>/kb.yaml`; devuelve el manifiesto o los errores V0."""
    path = root / MANIFEST
    if not path.is_file():
        raise KnowledgeBaseNotFound(f"no hay {MANIFEST} en {root}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        return None, [_v0(f"kb.yaml no es YAML: {error}")]
    if not isinstance(data, dict) or not isinstance(data.get("kb"), dict):  # pyright: ignore[reportUnknownMemberType]
        return None, [_v0("kb.yaml debe tener una raíz 'kb:' con un mapa")]
    try:
        return KbManifest.model_validate(data["kb"]), []
    except PydanticValidationError as error:
        return None, [_v0(f"{'.'.join(map(str, e['loc']))}: {e['msg']}") for e in error.errors()]


def _v0(message: str) -> ValidationError:
    return ValidationError(rule="V0", origin="kb", path=MANIFEST, message=message)
