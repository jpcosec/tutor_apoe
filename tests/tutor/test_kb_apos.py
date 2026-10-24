"""La KB `kbs/apos` abre con `kb`, valida, conserva los ids de `desk/atoms/` y responde a la
fachada `tutor.world` con el `HashEmbedder` (sin red)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tutor import world
from tutor.embedding import HASH_ID, HashEmbedder, get_embedder
from tutor.kb_build import plan, read_atoms, synthesize_branches

ACTION_BRANCH = "branch-apos-core-structures-action"
ACTION_ATOMS = {
    "atom-action-is-a-core-mental-structure-in-apos",
    "atom-action-requires-explicit-step-by-step-external-guidance",
    "atom-apos-defines-four-core-mental-structures",
}


def test_kb_opens_and_validates(kb) -> None:
    assert kb.name == "apos"
    report = kb.validate()
    assert report.is_valid, [error.line() for error in report.errors]


def test_counts(kb) -> None:
    assert len(kb.by_model("KnowledgeAtom", include_subclasses=False)) == 89
    assert len(kb.by_model("SourceAtom")) == 5
    assert len(kb.by_model("KnowledgeAtom")) == 94
    assert len(world.list_atoms(kb)) == 94
    assert len(kb.by_model("BranchNode")) >= 47
    assert kb.stats().relations_by_type == {"child_of": len(kb.by_model("KnowledgeAtom")) + len(kb.by_model("BranchNode")) - 2}


def test_ids_preserved(kb) -> None:
    source_ids = {
        m.group(1)
        for path in (world.repo_root() / "desk" / "atoms").rglob("*.md")
        if (m := re.search(r"^id: (\S+)$", path.read_text(encoding="utf-8"), re.M))
    }
    assert len(source_ids) == 141
    in_kb = {d.name for d in kb.by_model("KnowledgeAtom")} | {d.name for d in kb.by_model("BranchNode")}
    assert source_ids <= in_kb


def test_children_of_action_branch(kb) -> None:
    kids = world.children(kb, ACTION_BRANCH)
    assert {k["id"] for k in kids} == ACTION_ATOMS
    assert all(k["model"] == "KnowledgeAtom" and k["parent"] == ACTION_BRANCH for k in kids)


def test_parent_and_get(kb) -> None:
    atom = world.get_atom(kb, "atom-action-is-a-core-mental-structure-in-apos")
    assert atom is not None
    assert atom["question"] == "what"
    assert "topic:action" in atom["tags"]
    assert atom["summary"].startswith("APOS incluye la Acción")
    assert atom["provenance"].startswith("Fuente principal")
    assert world.parent(kb, atom["id"])["id"] == ACTION_BRANCH
    assert world.parent(kb, ACTION_BRANCH)["id"] == "branch-apos-core-structures"
    assert world.parent(kb, "branch-apos") is None
    assert world.get_atom(kb, "no-existe") is None


def test_rank_encapsulation_with_hash_embedder(kb) -> None:
    hits = world.rank(kb, "qué es encapsulación", 5)
    assert len(hits) == 5
    tagged = {d.name for d in kb.by_tag("topic:encapsulation")}
    assert any(atom_id in tagged for atom_id, _ in hits), hits
    assert hits == sorted(hits, key=lambda h: -h[1])


def test_role_projection_and_agent(kb) -> None:
    projection = world.role_projection(kb, "tutor")
    assert set(projection.models) == {"KnowledgeAtom", "BranchNode"}
    assert projection.relations == ["child_of"]
    visible = {d.name for d in kb.in_projection("tutor")}
    assert {d.name for d in kb.by_model("KnowledgeAtom")} <= visible
    assert "agent-tutor-apos" not in visible
    agent = world.agent(kb, "tutor")
    assert agent is not None and agent["projection"] == "tutor"
    assert "APOS" in agent["framing"] and "No inventes" in agent["instructions"]


def test_hash_embedder_is_deterministic_and_default() -> None:
    embedder = HashEmbedder()
    [a], [b] = embedder.embed(["Encapsulación"]), embedder.embed(["encapsulacion"])
    assert len(a) == 256 and a == b
    assert abs(sum(x * x for x in a) - 1.0) < 1e-9
    assert embedder.id() == HASH_ID
    assert isinstance(get_embedder(None), HashEmbedder)
    assert isinstance(get_embedder("hash"), HashEmbedder)


def test_build_plan_from_source_atoms(kb_root: Path) -> None:
    atoms_dir = world.repo_root() / "desk" / "atoms"
    atoms = read_atoms(atoms_dir)
    assert len(atoms) == 141
    synthesized = synthesize_branches(atoms)
    assert {b.id for b in synthesized} >= {"branch-apos", "branch-apos-core-structures"}
    built = plan(atoms, atoms_dir, None, HASH_ID)
    models = {doc.model for doc in built.docs}
    assert models == {
        "KnowledgeAtom", "SourceAtom", "BranchNode", "RelationTypeDoc", "RelationDoc",
        "TagNamespaceDoc", "AgentDoc", "ProjectionDoc",
    }
    assert built.manifest["kb"]["index"]["embedder_id"] == HASH_ID
    assert (kb_root / "kb.yaml").is_file()


@pytest.mark.parametrize("name", ["fastembed:modelo-inexistente", "fastembed"])
def test_get_embedder_fastembed_name_does_not_need_network(name: str) -> None:
    embedder = get_embedder(name)
    assert embedder.id().startswith(("fastembed:", "hash:"))
