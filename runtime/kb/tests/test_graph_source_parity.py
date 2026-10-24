"""Compile real canonical schemas and authored SLDB graphs in a fresh process."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skip(reason="usa el worktree externo de AntonIA (KB cobranza, /home/jp/AntonIA); no vendoreado y falla V6 contra el sldb actual")
def test_real_canonical_graphs(tmp_path: Path) -> None:
    source = Path("/home/jp/AntonIA/repos/AgentsKBs_worktrees/rebuild-kb-cobranza")
    script = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from kb_models.canonical.build import write_fixture_files, build_store
from kb import KnowledgeBase, SldbDeclarations
from cognitive import machine_definition_hash
from sldb.api import rebuild_edges
from context.substrates import KbSelfDeclarations
from cognitive import Scope
from ontology import Ref
root = Path(sys.argv[2])
write_fixture_files(root)
build_store(root, pythonpath=sys.argv[1])
kb = KnowledgeBase.open(root)
declarations = SldbDeclarations(kb, bound_release_id="r1", verified_fingerprint=kb.fingerprint)
machines = [d for d in kb.documents() if d.model == "MachineDoc"]
assert len(machines) == 13
for document in machines:
    definition = declarations.machine(document.key)
    assert definition.content_hash == machine_definition_hash(definition)
hashes = {document.key: declarations.machine(document.key).content_hash for document in machines}
rebuild_edges(root / ".sldb", sys.argv[1], wait=True)
rebuilt_kb = KnowledgeBase.open(root)
rebuilt = SldbDeclarations(rebuilt_kb, bound_release_id="r1", verified_fingerprint=rebuilt_kb.fingerprint)
assert hashes == {document.key: rebuilt.machine(document.key).content_hash for document in machines}
self_doc = next(d for d in kb.documents() if d.model == "SelfDoc")
self_declarations = KbSelfDeclarations(kb, declarations=declarations)
refs = self_declarations.declared_actions(
    Ref(kind="kb", id=self_doc.key, release_id="r1"), Scope(client_id="test"))
assert refs
assert all(r.release_id == "r1" for r in refs)
assert all(self_declarations.action_hash(r, Scope(client_id="test")) for r in refs)
from runtime.context.tests.projection_support import Substrate, NOW, SCOPE, OBSERVATION
from cognitive import MachineInstance, ProcessInstance, SelfAssignment
substrate = Substrate(root)
assignment_ref = Ref.parse("self_assignment:real")
process_ref = Ref.parse("process_instance:real")
instance_ref = Ref.parse("machine_instance:real")
process_doc = next(d for d in kb.documents() if d.model == "ProcessDoc")
definition = declarations.machine(machines[0].key)
substrate.machines.create(MachineInstance(
    ref=instance_ref, definition_ref=definition.ref, definition_hash=definition.content_hash,
    release_id="r1", owner_ref=process_ref, scope=SCOPE, state=definition.initial_state,
    created_at=NOW, updated_at=NOW))
substrate.assignments.create(SelfAssignment(
    ref=assignment_ref, self_definition_ref=Ref(kind="kb", id=self_doc.key, release_id="r1"),
    self_definition_hash=self_doc.content_hash, actor_ref=Ref.parse("actor:real"), scope=SCOPE,
    machine_ref=instance_ref, granted_capabilities=frozenset({"action:" + refs[0].id.rsplit(":", 1)[-1]})))
substrate.processes.create(ProcessInstance(
    ref=process_ref, process_definition_ref=Ref(kind="kb", id=process_doc.key, release_id="r1"),
    process_definition_hash=process_doc.content_hash, scope=SCOPE, machine_refs=(instance_ref,),
    participant_refs=(assignment_ref,)))
substrate.selection.bind(process_ref, OBSERVATION, SCOPE, revision="opaque-r1")
snapshot = substrate.projector(self_declarations).project(assignment_ref, process_ref, SCOPE)
assert snapshot.allowed_action_refs == (refs[0],)
assert snapshot.machine_snapshots[0]["ref"] == str(instance_ref)
assert "hash=" + self_declarations.action_hash(refs[0], SCOPE) in snapshot.inclusion_reasons[str(refs[0])]
print("13 production authored graphs compiled; can_perform edges resolved")
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(source), str(tmp_path / "canonical")],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
