"""`tutor.compiler` sin red: KB temporal con dos átomos y una fuente ingerida; un `FunctionModel`
devuelve propuestas fijas (una válida, una con parent inexistente, una duplicada) → acepta 1 y rechaza 2
con razones; el propuesto no entra a `build_context`; `approve` lo convierte y entonces sí entra;
`reject`; `gaps` con `FakeJevClient`; índice de fragmentos cacheado; `register_cli` y `register_mcp`."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from kb import KnowledgeBase
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from tutor import authoring, compiler, ingest, world
from tutor.agent import build_context
from tutor.authoring import AuthoringError
from tutor.embedding import HashEmbedder
from tutor.selector_jev import FakeJevClient

KB = "demo"
BRANCH = "branch-mecanismos"
SOURCE_TEXT = (
    "The ACE Teaching Cycle has three components: Activities, Classroom discussion, and Exercises. "
    "Activities are done by students in groups, usually on the computer, to build the mental constructions "
    "called for by the genetic decomposition.\n\n"
    "Thematization of a schema is the mechanism by which an individual comes to see a schema as a totality, "
    "a cognitive object to which actions and processes can be applied.\n\n"
    "Encapsulation converts a process into an object when the individual becomes aware of the process as a totality."
)
STATE: dict[str, Any] = {}


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("kbs")
    authoring.create_kb(KB, "Demo compilador", root=base)
    authoring.upsert_branch(KB, {"id": BRANCH, "title": "Mecanismos", "parent": f"branch-{KB}", "summary": "Cómo se construye"}, root=base)
    authoring.upsert_atom(KB, {"title": "La encapsulación convierte procesos en objetos", "question": "what", "answer": "Un proceso concebido como totalidad se encapsula en un objeto sobre el que se aplican nuevas acciones.", "provenance": "test", "tags": ["topic:encapsulation", f"system:{KB}"], "parent": BRANCH}, root=base)
    authoring.upsert_atom(KB, {"title": "La interiorización convierte acciones en procesos", "question": "how", "answer": "Repetir y reflexionar sobre una acción la interioriza en un proceso.", "provenance": "test", "tags": ["topic:interiorization", f"system:{KB}"], "parent": BRANCH}, root=base)
    ingested = ingest.ingest_text(KB, "Apunte APOS", SOURCE_TEXT, chunk_chars=260, root=base)
    STATE["chunks"] = [c["chunk_id"] for c in ingested["chunks"]]
    assert len(STATE["chunks"]) >= 2
    return base


def _proposal(title: str, answer: str, parent: str = BRANCH, chunk: str | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "title": title,
        "question": "what",
        "answer": answer,
        "provenance": {"chunk_ids": [chunk or STATE["chunks"][0]], "quote": "three components: Activities, Classroom discussion, and Exercises", "where": "p. 1"},
        "tags": ["topic:ace-cycle", "layer:pedagogy"],
        "parent": parent,
        "rationale": "La KB no tenía nada sobre el ciclo ACE.",
        **extra,
    }


def fixed_model(proposals: list[dict[str, Any]]) -> FunctionModel:
    """Un modelo que responde siempre con las mismas propuestas (tool de salida estructurada)."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args={"response": proposals})])

    return FunctionModel(respond, model_name="fixed")


class GroundedStub:
    """Cliente Jev de un solo noul fijo, con el contrato de `system_one`."""

    def __init__(self, noul: float) -> None:
        self.noul, self.calls = noul, []

    def system_one(self, state: Any, questions: Any, *, model: str | None = None) -> Any:
        self.calls.append((state, questions))
        return SimpleNamespace(answers={name: SimpleNamespace(noul=self.noul) for name in questions})


# -- índice de fragmentos -------------------------------------------------------------------


def test_chunk_index_is_cached_and_invalidated(root: Path) -> None:
    first = compiler.chunk_index(KB, root)
    assert len(first) == len(STATE["chunks"]) and first.cached is False
    cache = root / KB / compiler.CACHE_DIR
    assert list(cache.glob("chunks-*.json"))
    assert compiler.chunk_index(KB, root).cached is True
    ingest.ingest_text(KB, "Otra fuente", "Un texto breve sobre esquemas y su tematización como totalidad.", root=root)
    again = compiler.chunk_index(KB, root)
    assert again.cached is False and len(again) == len(STATE["chunks"]) + 1


def test_search_chunks_ranks_by_similarity(root: Path) -> None:
    hits = compiler.search_chunks(KB, "ACE teaching cycle activities classroom discussion exercises", k=2, root=root)
    assert hits[0]["chunk_id"] == STATE["chunks"][0] and hits[0]["score"] > hits[1]["score"]
    assert {"chunk_id", "source", "index", "page", "score", "text"} <= set(hits[0])


# -- compile: acepta 1, rechaza 2 -----------------------------------------------------------


def test_compile_accepts_one_rejects_two(root: Path) -> None:
    proposals = [
        _proposal("El ciclo ACE tiene tres componentes", "El ciclo de enseñanza ACE consta de actividades, discusión en clase y ejercicios."),
        _proposal("Las actividades ACE se hacen en grupo", "Las actividades se realizan en grupos, normalmente con computadora.", parent="branch-no-existe"),
        _proposal("Encapsular convierte un proceso en objeto", "Un proceso concebido como totalidad se encapsula en un objeto sobre el que se aplican nuevas acciones."),
    ]
    result = compiler.compile(KB, "el ciclo ACE y sus actividades", agent_model=fixed_model(proposals), max_atoms=5, root=root, jev_client=GroundedStub(0.2))
    assert isinstance(result, compiler.CompileResult) and result.written is True
    assert result.model == "function:fixed" and result.usage and result.usage["requests"] == 1
    assert [p["id"] for p in result.proposals] == ["atom-el-ciclo-ace-tiene-tres-componentes"]
    accepted = result.proposals[0]
    assert accepted["status"] == "proposed" and accepted["grounded"] is False and accepted["grounded_noul"] == 0.2
    assert f"system:{KB}" in accepted["tags"] and accepted["chunk_ids"] == [STATE["chunks"][0]]
    assert STATE["chunks"][0] in accepted["provenance"] and "«three components" in accepted["provenance"] and "Apunte APOS" in accepted["provenance"]
    assert (root / KB / "proposed" / f"{accepted['id']}.md").is_file()
    reasons = {r["title"]: r["reasons"] for r in result.rejected}
    assert len(reasons) == 2
    assert any("parent 'branch-no-existe' no existe" in why for why in reasons["Las actividades ACE se hacen en grupo"])
    assert any(why.startswith("duplicado de atom-la-encapsulacion-convierte-procesos-en-objetos") for why in reasons["Encapsular convierte un proceso en objeto"])
    assert authoring.validate_kb(KB, root)["ok"]
    STATE["proposed"] = accepted["id"]


def test_compile_rejects_unknown_chunks_and_dry_run_writes_nothing(root: Path) -> None:
    proposals = [_proposal("La discusión en clase sigue a las actividades", "La discusión en clase viene después de las actividades.", chunk="source-apunte-apos-chunk-99")]
    result = compiler.compile(KB, "discusión en clase", agent_model=fixed_model(proposals), root=root, write=False, jev_client=GroundedStub(0.9))
    assert result.proposals == [] and result.written is False
    assert "fragmentos inexistentes" in result.rejected[0]["reasons"][0]
    ok = [_proposal("La discusión en clase sigue a las actividades", "La discusión en clase viene después de las actividades.")]
    dry = compiler.compile(KB, "discusión en clase", agent_model=fixed_model(ok), root=root, write=False, jev_client=GroundedStub(0.9))
    assert dry.proposals[0]["grounded"] is True and dry.written is False and dry.proposals[0]["path"] is None
    assert not (root / KB / "proposed" / f"{dry.proposals[0]['id']}.md").exists()


def test_compile_without_chunks_or_request_fails_clearly(root: Path, tmp_path: Path) -> None:
    authoring.create_kb("vacia", "Sin fuentes", root=tmp_path)
    with pytest.raises(AuthoringError, match="no tiene fragmentos"):
        compiler.compile("vacia", "algo", agent_model=fixed_model([]), root=tmp_path)
    with pytest.raises(AuthoringError, match="vacía"):
        compiler.compile(KB, "   ", agent_model=fixed_model([]), root=root)


# -- el propuesto no contamina al tutor; approve lo convierte; reject ---------------------------


def test_proposed_is_invisible_to_tutor(root: Path) -> None:
    kb = KnowledgeBase.open(root / KB, HashEmbedder())
    proposed = STATE["proposed"]
    assert kb.get(proposed).model == "ProposedAtom"
    assert "ProposedAtom" not in {d.model for d in kb.in_projection("tutor")}
    mesa = build_context(kb, "¿Cuáles son los tres componentes del ciclo ACE?", k=8)
    assert proposed not in mesa["atom_ids"], mesa
    assert "atom-la-encapsulacion-convierte-procesos-en-objetos" in build_context(kb, "¿Qué es la encapsulación?", k=8)["atom_ids"]
    assert proposed not in {name for name, _ in world.rank(kb, "ciclo ACE tres componentes actividades", 10)}
    listed = compiler.list_proposed(KB, "proposed", root)
    assert [p["id"] for p in listed] == [proposed] and listed[0]["request"] == "el ciclo ACE y sus actividades"
    shown = compiler.get_proposed(KB, proposed, root)
    assert shown["markdown"].startswith("---\nid: " + proposed) and "## Justificación" in shown["markdown"]


def test_approve_converts_and_tutor_sees_it(root: Path) -> None:
    proposed = STATE["proposed"]
    result = compiler.approve(KB, proposed, root)
    assert result["approved"] == proposed and result["model"] == "KnowledgeAtom" and result["parent"] == BRANCH
    assert not (root / KB / "proposed" / f"{proposed}.md").exists()
    assert (root / KB / "knowledge" / f"{proposed}.md").is_file()
    kb = KnowledgeBase.open(root / KB, HashEmbedder())
    assert kb.validate().is_valid
    atom = kb.get(proposed)
    assert atom.model == "KnowledgeAtom" and compiler.COMPILER_MARK in atom.payload["provenance"][0]["note"]
    assert atom.payload["provenance"][0]["chunk_ids"] == [STATE["chunks"][0]] and atom.payload["provenance"][0]["kind"] == "book"
    assert atom.payload["citation"].startswith("source-apunte-apos") and "«three components" in atom.payload["citation"]
    assert world.parent(kb, proposed)["id"] == BRANCH
    mesa = build_context(kb, "¿Cuáles son los tres componentes del ciclo ACE?", k=8)
    assert proposed in mesa["atom_ids"], mesa
    assert [a["id"] for a in compiler.list_proposed(KB, "approved", root)] == [proposed]
    assert compiler.list_proposed(KB, "proposed", root) == []
    with pytest.raises(AuthoringError, match="no un propuesto"):
        compiler.approve(KB, proposed, root)


def test_reject_keeps_it_out_with_a_reason(root: Path) -> None:
    proposals = [_proposal("La tematización hace del esquema un objeto", "La tematización es el mecanismo por el que un esquema se ve como totalidad, un objeto al que aplicar acciones.", chunk=STATE["chunks"][1])]
    result = compiler.compile(KB, "qué es la tematización de un esquema", agent_model=fixed_model(proposals), root=root, jev_client=None)
    atom_id = result.proposals[0]["id"]
    assert result.proposals[0]["grounded"] is None or isinstance(result.proposals[0]["grounded"], bool)
    rejected = compiler.reject(KB, atom_id, "redundante con la rama de esquemas", root)
    assert rejected["status"] == "rejected" and rejected["rejected_why"] == "redundante con la rama de esquemas"
    assert [p["id"] for p in compiler.list_proposed(KB, "rejected", root)] == [atom_id]
    assert compiler.list_proposed(KB, "proposed", root) == []
    kb = KnowledgeBase.open(root / KB, HashEmbedder())
    assert kb.validate().is_valid and kb.get(atom_id).model == "ProposedAtom"
    assert atom_id not in build_context(kb, "¿Qué es la tematización de un esquema?")["atom_ids"]
    STATE["rejected"] = atom_id


# -- gaps -----------------------------------------------------------------------------------


def test_gaps_with_fake_jev(root: Path) -> None:
    client = FakeJevClient()
    result = compiler.gaps(KB, ["¿Qué es la encapsulación de un proceso?", "¿Qué dice la teoría sobre fractales cuánticos?"], root=root, client=client)
    assert result["jev"] is True and result["n_questions"] == 2
    covered, missing = result["rows"]
    assert covered["gap"] is False and covered["max_noul"] >= 0.5 and covered["best_atom"] == "atom-la-encapsulacion-convierte-procesos-en-objetos"
    assert missing["gap"] is True and missing["max_noul"] < 0.5
    assert result["gaps"] == [missing["question"]] and result["n_gaps"] == 1
    assert client.calls and all("student_question" in c["state"] for c in client.calls)
    assert STATE["rejected"] not in {i for row in result["rows"] for i, _ in row["top"]}


def test_gaps_without_jev_marks_unknown(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    result = compiler.gaps(KB, ["¿Qué es la encapsulación?"], root=root)
    assert result["jev"] is False and result["rows"][0]["gap"] is None and result["n_gaps"] == 0
    with pytest.raises(AuthoringError, match="no hay preguntas"):
        compiler.gaps(KB, [], root=root)


def test_load_questions_yaml_and_txt(tmp_path: Path) -> None:
    yaml_file = tmp_path / "q.yaml"
    yaml_file.write_text("questions:\n  - id: q1\n    question: '¿Qué es una acción?'\n  - '¿Y un proceso?'\n", encoding="utf-8")
    assert compiler.load_questions(yaml_file) == ["¿Qué es una acción?", "¿Y un proceso?"]
    txt = tmp_path / "q.txt"
    txt.write_text("# comentario\n¿Qué es un objeto?\n\n", encoding="utf-8")
    assert compiler.load_questions(txt) == ["¿Qué es un objeto?"]


# -- CLI y MCP --------------------------------------------------------------------------------


def test_register_cli(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from tutor.cli import app

    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    runner = CliRunner()
    kb_path = str(root / KB)
    listed = runner.invoke(app, ["compile", "list", "--kb", kb_path, "--status", "all"])
    assert listed.exit_code == 0, listed.output
    assert STATE["rejected"] in listed.output and "rejected" in listed.output
    shown = runner.invoke(app, ["compile", "show", STATE["rejected"], "--kb", kb_path])
    assert shown.exit_code == 0 and "rejected_why: redundante" in shown.output, shown.output
    approved = runner.invoke(app, ["compile", "list", "--kb", kb_path, "--status", "approved"])
    assert approved.exit_code == 0 and STATE["proposed"] in approved.output
    missing = runner.invoke(app, ["compile", "show", "atom-nada", "--kb", kb_path])
    assert missing.exit_code == 1 and "error:" in missing.output
    questions = root / "q.txt"
    questions.write_text("¿Qué es la encapsulación?\n", encoding="utf-8")
    gaps = runner.invoke(app, ["compile", "gaps", "--kb", kb_path, "--questions", str(questions)])
    assert gaps.exit_code == 0 and "Jev no disponible" in gaps.output, gaps.output
    source = root / "extra.md"
    source.write_text("Un apunte más sobre la coordinación de procesos.\n", encoding="utf-8")
    ingested = runner.invoke(app, ["compile", "ingest", str(source), "--kb", kb_path, "--title", "Extra"])
    assert ingested.exit_code == 0 and "source-extra: 1 fragmentos" in ingested.output, ingested.output
    assert runner.invoke(app, ["compile", "--help"]).exit_code == 0
    assert {"run", "list", "show", "approve", "reject", "ingest", "gaps"} <= set(runner.invoke(app, ["compile", "--help"]).output.split())


def test_register_mcp(root: Path) -> None:
    from mcp.client.client import Client

    from tutor import mcp_server
    from tutor.mcp_server import tool_result

    server = mcp_server.build(root)

    async def go() -> Any:
        async with Client(server) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            listed = tool_result(await client.call_tool("list_proposed", {"kb_id": KB, "status": "rejected"}))
            bad = tool_result(await client.call_tool("approve_atom", {"kb_id": KB, "atom_id": "atom-nada"}))
            rejected_again = tool_result(await client.call_tool("reject_atom", {"kb_id": KB, "atom_id": STATE["rejected"], "why": "sigue sobrando"}))
            approved = tool_result(await client.call_tool("list_proposed", {"kb_id": KB, "status": "approved"}))
            source = root / "mcp.txt"
            source.write_text("Texto para ingest_pdf por MCP.\n\nOtro párrafo.\n", encoding="utf-8")
            ingested = tool_result(await client.call_tool("ingest_pdf", {"kb_id": KB, "path": str(source), "title": "Via MCP"}))
            return names, listed, bad, rejected_again, approved, ingested

    names, listed, bad, rejected_again, approved, ingested = asyncio.run(go())
    assert {"compile_atoms", "list_proposed", "approve_atom", "reject_atom", "ingest_pdf", "find_gaps"} <= names
    assert [a["id"] for a in listed["atoms"]] == [STATE["rejected"]]
    assert set(bad) == {"error", "hint"}
    assert rejected_again["rejected_why"] == "sigue sobrando"
    assert [a["id"] for a in approved["atoms"]] == [STATE["proposed"]]
    assert ingested["source_id"] == "source-via-mcp" and ingested["index_size"] >= 4
