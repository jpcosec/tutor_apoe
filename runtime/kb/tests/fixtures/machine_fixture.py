"""Fixture de máquinas: monta stores `.sldb` REALES con modelos de máquina (canonical)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_sequence = 0

FIXTURE_MODELS = """
from pydantic import Field
from sldb import StructuredNLDoc

class MachineDoc(StructuredNLDoc):
    __family__ = "machine"
    __references__ = ["initial_state_ref"]
    __template__ = (
        "---\\n"
        "id: ⸢rev•id⸥\\n"
        "title: ⸢rev•title⸥\\n"
        "version: ⸢rev•version⸥\\n"
        "family: ⸢rev•family⸥\\n"
        "initial_state_ref: ⸢rev•initial_state_ref⸥\\n"
        "state_refs: ⸢rev,list•state_refs⸥\\n"
        "transition_refs: ⸢rev,list•transition_refs⸥\\n"
        "event_type_refs: ⸢rev,list•event_type_refs⸥\\n"
        "cardinality: ⸢rev•cardinality⸥\\n"
        "variables_schema: ⸢rev•variables_schema⸥\\n"
        "---\\n"
        "\\n"
        "# ⸢render•title⸥\\n"
        ""
    )
    id: str = Field(description="id"); title: str = Field(description="title")
    version: str = Field(description="version"); family: str = Field(description="family")
    initial_state_ref: str = Field(description="initial")
    state_refs: list[str] = Field(default_factory=list, description="states")
    transition_refs: list[str] = Field(default_factory=list, description="trans")
    event_type_refs: list[str] = Field(default_factory=list, description="events")
    cardinality: str = Field(default="many", description="card")
    variables_schema: dict = Field(default_factory=dict, description="variables")

class StateDoc(StructuredNLDoc):
    __family__ = "state"
    __template__ = (
        "---\\n"
        "id: ⸢rev•id⸥\\n"
        "title: ⸢rev•title⸥\\n"
        "machine_ref: ⸢rev•machine_ref⸥\\n"
        "terminal: ⸢rev•terminal⸥\\n"
        "---\\n"
        "\\n"
        "# ⸢render•title⸥\\n"
        ""
    )
    id: str = Field(description="id"); title: str = Field(description="title")
    machine_ref: str = Field(description="mach"); terminal: bool = Field(default=False, description="t")

class TransitionDoc(StructuredNLDoc):
    __family__ = "transition"
    __template__ = (
        "---\\n"
        "id: ⸢rev•id⸥\\n"
        "title: ⸢rev•title⸥\\n"
        "machine_ref: ⸢rev•machine_ref⸥\\n"
        "source_ref: ⸢rev•source_ref⸥\\n"
        "target_ref: ⸢rev•target_ref⸥\\n"
        "event_type_ref: ⸢rev•event_type_ref⸥\\n"
        "priority: ⸢rev•priority⸥\\n"
        "guard_refs: ⸢rev,list•guard_refs⸥\\n"
        "action_refs: ⸢rev,list•action_refs⸥\\n"
        "assignments: ⸢rev•assignments⸥\\n"
        "---\\n"
        "\\n"
        "# ⸢render•title⸥\\n"
        ""
    )
    id: str = Field(description="id"); title: str = Field(description="title")
    machine_ref: str = Field(description="mach"); source_ref: str = Field(description="s")
    target_ref: str = Field(description="t"); event_type_ref: str = Field(description="ev")
    priority: int = Field(default=0, description="p")
    guard_refs: list[str] = Field(default_factory=list, description="g")
    action_refs: list[str] = Field(default_factory=list, description="a")
    assignments: dict = Field(default_factory=dict, description="bindings")

class EventTypeDoc(StructuredNLDoc):
    __family__ = "event"
    __template__ = (
        "---\\n"
        "id: ⸢rev•id⸥\\n"
        "title: ⸢rev•title⸥\\n"
        "machine_ref: ⸢rev•machine_ref⸥\\n"
        "name: ⸢rev•name⸥\\n"
        "payload_schema: ⸢rev•payload_schema⸥\\n"
        "---\\n"
        "\\n"
        "# ⸢render•title⸥\\n"
        ""
    )
    id: str = Field(description="id"); title: str = Field(description="title")
    machine_ref: str = Field(description="mach"); name: str = Field(description="name")
    payload_schema: dict = Field(default_factory=dict, description="schema")

class GuardDoc(StructuredNLDoc):
    __family__ = "guard"
    __template__ = (
        "---\\n"
        "id: ⸢rev•id⸥\\n"
        "title: ⸢rev•title⸥\\n"
        "machine_ref: ⸢rev•machine_ref⸥\\n"
        "expression: ⸢rev•expression⸥\\n"
        "---\\n"
        "\\n"
        "# ⸢render•title⸥\\n"
        ""
    )
    id: str = Field(description="id"); title: str = Field(description="title")
    machine_ref: str = Field(description="mach")
    expression: dict = Field(default_factory=dict, description="expr")

class ActionDoc(StructuredNLDoc):
    __family__ = "action"
    __template__ = (
        "---\\n"
        "id: ⸢rev•id⸥\\n"
        "title: ⸢rev•title⸥\\n"
        "---\\n"
        "\\n"
        "# ⸢render•title⸥\\n"
        ""
    )
    id: str = Field(description="id"); title: str = Field(description="title")
"""

MODEL_NAMES = ("MachineDoc", "StateDoc", "TransitionDoc", "EventTypeDoc", "GuardDoc", "ActionDoc")

RELATION_TYPES = {
    "has_state": (["MachineDoc"], ["StateDoc"], "one_to_many"),
    "has_transition": (["MachineDoc"], ["TransitionDoc"], "one_to_many"),
    "starts_at": (["MachineDoc"], ["StateDoc"], "one_to_one"),
    "transition_from": (["TransitionDoc"], ["StateDoc"], "many_to_many"),
    "transition_to": (["TransitionDoc"], ["StateDoc"], "many_to_many"),
    "triggered_by": (["TransitionDoc"], ["EventTypeDoc"], "many_to_one"),
    "guarded_by": (["TransitionDoc"], ["GuardDoc"], "many_to_many"),
    "invokes_action": (["TransitionDoc"], ["ActionDoc"], "many_to_many"),
}


@dataclass
class MachineStore:
    root: Path
    store: Path
    pythonpath: str


def default_docs() -> list[tuple[str, str, dict[str, object]]]:
    return [
        (
            "MachineDoc",
            "m1.md",
            {
                "id": "m1",
                "title": "M1",
                "version": "1.0",
                "family": "consent",
                "initial_state_ref": "StateDoc:st-1",
                "state_refs": ["StateDoc:st-1", "StateDoc:st-2"],
                "transition_refs": ["TransitionDoc:t1"],
                "event_type_refs": ["EventTypeDoc:ev-app"],
                "cardinality": "many",
            },
        ),
        ("StateDoc", "st-1.md", {"id": "st-1", "title": "s1", "machine_ref": "MachineDoc:m1"}),
        (
            "StateDoc",
            "st-2.md",
            {"id": "st-2", "title": "s2", "machine_ref": "MachineDoc:m1", "terminal": True},
        ),
        (
            "EventTypeDoc",
            "ev-app.md",
            {
                "id": "ev-app",
                "title": "app",
                "machine_ref": "MachineDoc:m1",
                "name": "approve",
                "payload_schema": {"type": "object", "properties": {"amt": {"type": "number"}}},
            },
        ),
        (
            "TransitionDoc",
            "t1.md",
            {
                "id": "t1",
                "title": "t1",
                "machine_ref": "MachineDoc:m1",
                "source_ref": "StateDoc:st-1",
                "target_ref": "StateDoc:st-2",
                "event_type_ref": "EventTypeDoc:ev-app",
                "priority": 0,
                "guard_refs": [],
                "action_refs": [],
            },
        ),
    ]


def default_edges() -> list[tuple[str, str, str]]:
    return [
        ("has_state", "MachineDoc:m1", "StateDoc:st-1"),
        ("has_state", "MachineDoc:m1", "StateDoc:st-2"),
        ("starts_at", "MachineDoc:m1", "StateDoc:st-1"),
        ("has_transition", "MachineDoc:m1", "TransitionDoc:t1"),
        ("transition_from", "TransitionDoc:t1", "StateDoc:st-1"),
        ("transition_to", "TransitionDoc:t1", "StateDoc:st-2"),
        ("triggered_by", "TransitionDoc:t1", "EventTypeDoc:ev-app"),
    ]


def build_machine_store(
    tmp_path: Path,
    docs: list[tuple[str, str, dict[str, object]]] | None = None,
    edges: list[tuple[str, str, str]] | None = None,
) -> MachineStore:
    """Monta un store `.sldb` REAL con modelos de máquina y aristas tipadas.

    Cada llamada construye en un subdirectorio propio bajo `tmp_path`, evitando
    colisiones cuando un test monta varias versiones en el mismo `tmp_path`.
    """
    import yaml

    global _sequence

    build_dir = tmp_path / f"store-{_sequence}-{os.getpid()}"
    _sequence += 1
    root = build_dir
    root.mkdir(parents=True, exist_ok=True)
    pythonpath = str(root)
    from sldb.api import (
        add_model,
        create_document,
        init_relations,
        init_store,
        rebuild_edges,
    )

    (root / "_machine_models.py").write_text(FIXTURE_MODELS, encoding="utf-8")
    (root / "kb.yaml").write_text(
        yaml.safe_dump(
            {
                "kb": {
                    "name": "kb-machine",
                    "kb_version": 1,
                    "models": "_machine_models",
                    "pythonpath": ".",
                    "materialize": {"order": []},
                }
            }
        ),
        encoding="utf-8",
    )
    store = init_store(root).store_path
    init_relations(store, pythonpath)
    for name, (src, tgt, card) in RELATION_TYPES.items():
        create_document(
            store,
            "RelationTypeDoc",
            root / "rels" / f"{name}.md",
            {
                "title": name,
                "name": name,
                "direction": "directed",
                "cardinality": card,
                "axis": "TOPOLOGY",
                "source_types": src,
                "target_types": tgt,
                "condition": "",
                "description": name,
            },
            pythonpath=pythonpath,
        )
    for model in MODEL_NAMES:
        add_model(store, f"_machine_models:{model}", pythonpath=pythonpath)
    for model, name, fields in docs or default_docs():
        create_document(store, model, root / name, fields, pythonpath=pythonpath)
    for rt, src, tgt in edges or default_edges():
        relname = f"{rt}--{src.split(':')[-1]}--{tgt.split(':')[-1]}"
        create_document(
            store,
            "RelationDoc",
            root / "rels" / f"{relname}.md",
            {
                "title": f"{src} {rt} {tgt}",
                "source_id": src,
                "target_id": tgt,
                "relation_type": rt,
                "condition": "",
                "notes": "",
            },
            pythonpath=pythonpath,
        )
    rebuild_edges(store, pythonpath, wait=True)
    return MachineStore(root=root, store=store, pythonpath=pythonpath)


__all__ = [
    "MachineStore",
    "build_machine_store",
    "default_docs",
    "default_edges",
]
