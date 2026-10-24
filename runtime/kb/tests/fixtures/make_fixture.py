"""Construye KBs de prueba con las escrituras de sldb (spec 01 §8.1): se versiona el script, no el store."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from sldb.api import add_model, create_document, init_relations, init_store, rebuild_edges

FIXTURES = Path(__file__).parent
MODELS = ("Note", "SpecialNote", "Tool", "Trait", "Style", "Step", "Category", "Reference", "ToolCheck")


@dataclass
class Doc:
    model: str
    path: str
    fields: dict[str, Any]


@dataclass
class KbSpec:
    """Una KB de prueba: manifiesto (bajo `kb:`) y documentos."""

    docs: list[Doc]
    manifest: dict[str, Any] = field(default_factory=dict[str, Any])


def minimal() -> KbSpec:
    """La KB más chica que pasa, más un documento de cada tipo opcional."""
    return KbSpec(
        manifest={"materialize": {"order": ["notes"]}},
        docs=[
            Doc(
                "Note",
                "notes/nota-a.md",
                {"id": "nota-a", "title": "Nota A", "tags": ["topic:uno"], "body": "A."},
            ),
            Doc("SpecialNote", "notes/nota-b.md", special("nota-b")),
            Doc(
                "Tool",
                "self/tool-x.md",
                {"id": "tool-x", "title": "Tool X", "parameters": '{"name": "hacer_x"}'},
            ),
            Doc("RelationTypeDoc", "kgdb/relation_types/cites.md", relation_type("cites")),
            relation_doc("Note:nota-a", "SpecialNote:nota-b"),
        ],
    )


def build(spec: KbSpec, root: Path) -> Path:
    """Escribe `root/kb.yaml`, inicializa el store, registra los modelos y crea los documentos."""
    root.mkdir(parents=True, exist_ok=True)
    manifest = {"name": "kb-minima", "kb_version": 1, "models": "minimal_models", "pythonpath": str(FIXTURES)}
    (root / "kb.yaml").write_text(yaml.safe_dump({"kb": {**manifest, **spec.manifest}}), encoding="utf-8")
    store = init_store(root).store_path
    pythonpath = str(FIXTURES)
    init_relations(store, pythonpath)
    for model in MODELS:
        add_model(store, f"minimal_models:{model}", pythonpath=pythonpath)
    for doc in spec.docs:
        create_document(store, doc.model, root / doc.path, doc.fields, pythonpath=pythonpath)
    rebuild_edges(store, pythonpath, wait=True)
    return root


def special(name: str) -> dict[str, Any]:
    return {"id": name, "title": "Nota especial", "tags": ["topic:dos"], "body": "B.", "level": 2}


def relation_type(name: str) -> dict[str, Any]:
    return {
        "title": name,
        "name": name,
        "direction": "directed",
        "cardinality": "many_to_many",
        "axis": "WHY",
        "source_types": ["Note"],
        "target_types": ["Note"],
        "condition": "",
        "description": "Una nota cita a otra.",
    }


def relation(source: str, target: str, relation_type: str = "cites") -> dict[str, Any]:
    return {
        "title": f"{source} {relation_type} {target}",
        "source_id": source,
        "target_id": target,
        "relation_type": relation_type,
        "condition": "",
        "notes": "",
    }


def relation_doc(source: str, target: str, relation_type: str = "cites") -> Doc:
    """Un `RelationDoc` con el nombre de la norma: `<tipo>--<origen>--<destino>` (13 §4.0)."""
    name = f"{relation_type}--{source.split(':')[-1]}--{target.split(':')[-1]}"
    return Doc("RelationDoc", f"relations/{name}.md", relation(source, target, relation_type))
