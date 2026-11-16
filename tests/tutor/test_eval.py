"""`tutor.eval` sin red: citas y oraciones, métricas, `run_eval` con `model="test"` + `FakeJevClient`
(selector y groundedness) sobre 3 preguntas, report.md/compare, `explain_turn`, `atoms_health` detecta un
duplicado inducido en una KB temporal, y `register_cli`/`register_mcp` registran comandos y tools."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
import typer
from mcp.client.client import Client
from typer.testing import CliRunner

from tutor import authoring, eval as ev, mcp_server, world
from tutor.embedding import HashEmbedder
from tutor.selector_jev import FakeJevClient, FakeNoulAnswer, FakeResponse

ACTION = "atom-action-is-a-core-mental-structure-in-apos"
GUIDANCE = "atom-action-requires-explicit-step-by-step-external-guidance"
REPLY = (
    f"Una acción es una transformación externa [{ACTION}]. Necesita guía paso a paso "
    f"[{GUIDANCE}].\n\n- Esto no está en la KB [atom-inventado].\n"
    f"Otra idea [KnowledgeAtom:{ACTION}]. Sin cita final."
)


class SupportiveJev:
    """Noul alto si la oración comparte palabras con la respuesta del átomo citado (imita el Noul de
    groundedness sin depender del `student_question` que mira `FakeJevClient`)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def system_one(self, state: Any, questions: Any, *, model: str | None = None) -> FakeResponse:
        self.calls.append({"state": state, "questions": questions, "model": model})
        if "student_question" in state:  # llamada del selector
            return FakeJevClient().system_one(state, questions, model=model)
        claim = set(state["claim"].lower().split())
        atom = f"{state['cited_atom']['title']} {state['cited_atom']['answer']}".lower()
        overlap = len({w for w in claim if len(w) > 4 and w in atom})
        return FakeResponse({name: FakeNoulAnswer(0.9 if overlap >= 2 else 0.2) for name in questions})


@pytest.fixture(scope="module")
def questions() -> list[ev.EvalQuestion]:
    qs = ev.load_questions()
    assert len(qs) == 20
    return qs[:3]


# -- citas y oraciones ------------------------------------------------------------------------


def test_extract_citations_and_sentences() -> None:
    assert ev.extract_citations(REPLY) == [ACTION, GUIDANCE, "atom-inventado"]
    sentences = ev.split_sentences(REPLY)
    assert len(sentences) == 5 and sentences[2].startswith("Esto no está")
    cited = ev.cited_sentences(REPLY)
    assert [c["atom_ids"] for c in cited] == [[ACTION], [GUIDANCE], ["atom-inventado"], [ACTION]]
    # una cita suelta tras el punto se pega a su oración
    assert ev.cited_sentences("La acción es externa. [atom-x]")[0]["sentence"] == "La acción es externa. [atom-x]"


def test_citation_metrics() -> None:
    m = ev.citation_metrics(REPLY, mesa_ids=[ACTION], known_ids={ACTION, GUIDANCE}, expected_ids=[ACTION, GUIDANCE, "atom-otro"], reads=[])
    assert m["valid"] == [ACTION, GUIDANCE] and m["invalid"] == ["atom-inventado"]
    assert m["in_mesa"] == [ACTION] and m["out_of_mesa"] == [GUIDANCE]
    assert m["coverage"] == pytest.approx(2 / 3) and m["valid_rate"] == pytest.approx(2 / 3)
    # leído con show_atom cuenta como "en mesa"
    read = ev.citation_metrics(REPLY, mesa_ids=[ACTION], known_ids={ACTION, GUIDANCE}, expected_ids=[], reads=[GUIDANCE])
    assert read["out_of_mesa"] == [] and read["coverage"] is None


def test_retrieval_metrics_reuse_benchmark_formula(kb) -> None:
    q = ev.EvalQuestion("q", "x", (GUIDANCE,), ("topic:action",))
    tags = {a["id"]: a["tags"] for a in world.list_atoms(kb)}
    m = ev.retrieval_metrics(["atom-a", GUIDANCE, "atom-b"], q, 8, tags)
    assert m["scored"] and m["hit@1"] == 0 and m["hit@k"] == 1 and m["rr"] == 0.5 and m["tag_hit@k"] == 1
    assert ev.retrieval_metrics(["atom-a"], ev.EvalQuestion("q", "x"), 8, tags)["scored"] is False


def test_grounder_skipped_without_client(kb, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    result = ev.Grounder().check(REPLY, kb)
    assert result["status"] == "skipped" and result["n_claims"] == 4 and result["fraction_supported"] is None


def test_grounder_with_fake_client(kb) -> None:
    client = SupportiveJev()
    text = f"La Acción es una de las estructuras mentales de APOS [{ACTION}]. Los dinosaurios eran grandes [{GUIDANCE}]."
    result = ev.Grounder(client=client).check(text, kb)
    assert result["status"] == "ok" and result["n_claims"] == 2
    assert [c["supported"] for c in result["claims"]] == [True, False]
    assert result["unsupported"][0]["atom_ids"] == [GUIDANCE]
    assert client.calls[0]["state"]["cited_atom"]["id"] == ACTION and "claim" in client.calls[0]["state"]


# -- run / report / compare ---------------------------------------------------------------------


def test_run_eval_with_test_model_and_fake_jev(kb, questions, tmp_path: Path) -> None:
    results = ev.run_eval(kb=kb, questions=questions, model="test", selector="jev", k=8, jev_client=FakeJevClient())
    assert results["meta"]["selector"] == "jev" and results["meta"]["n_questions"] == 3
    s = results["summary"]
    assert s["n_ok"] == 3 and s["n_errors"] == 0
    assert s["retrieval"]["hit@8"] == 1.0 and s["retrieval"]["max_noul_mean"] > 0.5
    assert s["citations"]["valid_rate"] == 1.0 and s["citations"]["in_mesa_rate"] == 1.0 and s["citations"]["n_invalid_total"] == 0
    assert s["groundedness"]["status"] == "ok" and s["groundedness"]["n_claims"] > 0
    first = results["questions"][0]
    assert first["mesa"]["reasoning_log"] and first["retrieval"]["max_noul"] is not None
    assert first["answer"]["latency_ms"] > 0 and first["answer"]["requests"] == 1

    out = ev.write_run(results, tmp_path / "run-a")
    assert (out / "results.json").is_file() and (out / "report.md").is_file()
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "## Resumen" in report and "## Por pregunta" in report and "q01-accion" in report and "## Peores preguntas" in report
    assert ev.load_run(out)["meta"]["model"] == "test"
    assert ev.out_dir_for(results, tmp_path).name.endswith("-test-jev")

    heuristic = ev.run_eval(kb=kb, questions=questions, model="test", selector="heuristic", k=8)
    assert heuristic["meta"]["selector"] == "heuristic"
    assert heuristic["summary"]["groundedness"]["status"] in {"skipped", "ok"}
    comparison = ev.compare_runs(results, heuristic)
    assert "# Comparación" in comparison and "## Por pregunta (A/B)" in comparison and "q02-proceso" in comparison
    assert len(ev.worst_questions(results)) == 3


def test_run_eval_jev_falls_back_to_heuristic_without_key(kb, questions, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    results = ev.run_eval(kb=kb, questions=questions[:1], model="test", selector="auto")
    assert results["meta"]["selector"] == "heuristic"
    assert results["questions"][0]["retrieval"]["max_noul"] is None
    assert results["summary"]["groundedness"]["status"] == "skipped"


def test_explain_turn_finds_benchmark_question(kb, questions) -> None:
    record = ev.explain_turn("q01-accion", kb=kb, model="test", selector="heuristic", questions=questions)
    assert record["in_benchmark"] and record["expected_atom_ids"] == list(questions[0].expected_atom_ids)
    assert any(item["expected"] for item in record["mesa_view"])
    text = ev.render_turn(record)
    assert "mesa (" in text and "expected:" in text and "groundedness:" in text and "E = expected" in text
    free = ev.explain_turn("¿Qué es un esquema?", kb=kb, model="test", selector="heuristic", questions=questions)
    assert not free["in_benchmark"] and free["retrieval"]["scored"] is False


# -- atoms ----------------------------------------------------------------------------------------


def test_atoms_health_detects_induced_duplicate(tmp_path: Path) -> None:
    root = tmp_path / "kbs"
    authoring.create_kb("dup", "KB con duplicado", root=root)
    base = {"question": "what", "provenance": "test", "tags": ["topic:encapsulacion", "system:dup"], "parent": "branch-dup"}
    authoring.upsert_atom("dup", {**base, "title": "La encapsulación convierte procesos en objetos", "answer": "Un proceso concebido como una totalidad sobre la que pueden aplicarse nuevas acciones se encapsula en un objeto cognitivo."}, root)
    authoring.upsert_atom("dup", {**base, "title": "La encapsulacion convierte los procesos en objetos.", "answer": "Corta."}, root)
    authoring.upsert_atom("dup", {**base, "title": "La interiorización convierte acciones en procesos", "answer": "Repetir una acción y reflexionar sobre ella la interioriza en un proceso mental que ya no necesita estímulos externos.", "tags": ["topic:interiorizacion", "extra:nuevo"]}, root)
    authoring.upsert_branch("dup", {"title": "Rama vacía", "parent": "branch-dup", "summary": "nada"}, root)
    kb = world.open_kb(root / "dup", HashEmbedder(), build_if_missing=False)

    report = ev.atoms_health(kb, tmp_path / "no-evals")
    pairs = {(d["a"], d["b"]) for d in report["near_duplicate_titles"]}
    assert ("atom-la-encapsulacion-convierte-los-procesos-en-objetos", "atom-la-encapsulacion-convierte-procesos-en-objetos") in pairs
    assert len(pairs) == 1
    assert [s["id"] for s in report["short_answers"]] == ["atom-la-encapsulacion-convierte-los-procesos-en-objetos"]
    # `upsert_atom` declara los namespaces nuevos y el esquema rechaza tags sin `ns:`: nada que acusar
    assert report["undeclared_tags"] == [] and "extra" in report["declared_namespaces"]
    assert [b["id"] for b in report["branches_without_atoms"]] == ["branch-rama-vacia"]
    assert report["orphan_atoms"] == [] and report["no_provenance"] == []
    assert report["usage"]["n_runs"] == 0 and report["counts"]["near_duplicate_titles"] == 1
    text = ev.render_health(report)
    assert "títulos casi duplicados" in text and "sin corridas" in text


def test_atoms_health_usage_from_evals(kb, questions, tmp_path: Path) -> None:
    results = ev.run_eval(kb=kb, questions=questions, model="test", selector="heuristic")
    ev.write_run(results, tmp_path / "evals" / "run-1")
    report = ev.atoms_health(kb, tmp_path / "evals")
    usage = report["usage"]
    assert usage["n_runs"] == 1 and usage["n_in_mesa"] >= 3 and usage["n_cited"] >= 3
    assert usage["never_in_mesa_nor_cited"] and usage["most_used"][0]["cited"] >= 1
    assert "más usados" in ev.render_health(report)
    assert report["counts"]["orphan_atoms"] == 0 and report["counts"]["undeclared_tags"] == 0 and report["counts"]["no_provenance"] == 0


# -- registro CLI y MCP ---------------------------------------------------------------------------


def test_register_cli_adds_eval_commands(kb_root: Path, tmp_path: Path) -> None:
    app = typer.Typer()
    ev.register_cli(app)
    assert [g.name for g in app.registered_groups] == ["eval"]
    eval_app = app.registered_groups[0].typer_instance
    assert {c.name for c in eval_app.registered_commands} == {"run", "report", "compare", "turn", "atoms"}

    from tutor.cli import app as tutor_app

    runner = CliRunner()
    out = tmp_path / "run"
    result = runner.invoke(tutor_app, ["eval", "run", "--kb", str(kb_root), "--model", "test", "--selector", "heuristic", "--limit", "2", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "hit@1" in result.output and (out / "report.md").is_file()
    assert runner.invoke(tutor_app, ["eval", "report", str(out)]).exit_code == 0
    assert runner.invoke(tutor_app, ["eval", "compare", str(out), str(out)]).exit_code == 0
    turn = runner.invoke(tutor_app, ["eval", "turn", "--kb", str(kb_root), "--model", "test", "--selector", "heuristic", "q01-accion"])
    assert turn.exit_code == 0 and "benchmark q01-accion" in turn.output, turn.output
    atoms = runner.invoke(tutor_app, ["eval", "atoms", "--kb", str(kb_root), "--evals", str(tmp_path), "--json", str(tmp_path / "atoms.json")])
    assert atoms.exit_code == 0 and "átomos huérfanos" in atoms.output and json.loads((tmp_path / "atoms.json").read_text())["n_atoms"] > 0


def test_register_mcp_adds_tools(tmp_path: Path, kb_root: Path) -> None:
    server = mcp_server.build(kb_root.parent)

    async def go():
        async with Client(server) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            assert {"eval_run", "explain_turn", "eval_atoms"} <= set(tools)
            assert tools["eval_run"].annotations.open_world_hint is True and tools["eval_atoms"].annotations.read_only_hint is True
            atoms = mcp_server.tool_result(await client.call_tool("eval_atoms", {"kb_id": "apos", "evals_dir": str(tmp_path)}))
            assert atoms["n_atoms"] > 0 and "text" in atoms
            run = mcp_server.tool_result(await client.call_tool("eval_run", {"kb_id": "apos", "model": "test", "selector": "heuristic", "limit": 2, "out": str(tmp_path / "mcp-run")}))
            assert run["summary"]["n_ok"] == 2 and run["questions"][0]["mesa_atom_ids"] and "mesa" not in run["questions"][0]
            assert (tmp_path / "mcp-run" / "report.md").is_file()
            q01 = ev.load_questions()[0]
            own = mcp_server.tool_result(await client.call_tool("eval_run", {"kb_id": "apos", "model": "test", "selector": "heuristic", "questions": [{"question": q01.question, "expected_atom_ids": list(q01.expected_atom_ids)}]}))
            assert own["summary"]["retrieval"]["hit@8"] == 1.0
            turn = mcp_server.tool_result(await client.call_tool("explain_turn", {"kb_id": "apos", "question": "q02-proceso", "model": "test", "selector": "heuristic"}))
            assert turn["in_benchmark"] and "mesa (" in turn["text"]
            bad = mcp_server.tool_result(await client.call_tool("eval_run", {"kb_id": "no-existe"}))
            assert set(bad) == {"error", "hint"}

    asyncio.run(go())
