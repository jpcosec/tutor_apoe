"""`tutor.mcp_server` con el cliente en proceso de la SDK `mcp`: las tools están, el flujo
crear → poblar → buscar → turno → validar funciona en tmpdir, los recursos y prompts se leen, los
errores vuelven como `{error, hint}`, la autoprueba termina en 0 y el transporte HTTP exige el Bearer."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp.client.client import Client

from tutor import mcp_server
from tutor.mcp_server import tool_result

REPO = Path(__file__).resolve().parents[2]
EXPECTED_TOOLS = {
    "list_kbs", "create_kb", "validate_kb", "rebuild_kb", "kb_stats",
    "search_atoms", "get_atom", "list_branches", "children", "upsert_atom", "upsert_branch", "delete_atom", "link_atoms",
    "ingest_text", "ingest_file", "get_chunk",
    "list_tutors", "upsert_tutor", "run_turn", "inspect_context", "benchmark_tutor",
}


def run(coro):
    return asyncio.run(coro)


async def call(client: Client, name: str, **args: Any) -> dict[str, Any]:
    return tool_result(await client.call_tool(name, args))


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory):
    return mcp_server.build(tmp_path_factory.mktemp("kbs"))


def test_list_tools_resources_prompts(server) -> None:
    async def go():
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            prompts = (await client.list_prompts()).prompts
            templates = (await client.list_resource_templates()).resource_templates
            return tools, prompts, templates

    tools, prompts, templates = run(go())
    names = {t.name for t in tools}
    assert EXPECTED_TOOLS <= names, EXPECTED_TOOLS - names
    assert all(t.description for t in tools), "toda tool lleva docstring (la lee el LLM)"
    assert {p.name for p in prompts} == {"author_kb", "tutor_session"}
    assert {t.uri_template for t in templates} == {"tutor://{kb_id}/atom/{atom_id}", "tutor://{kb_id}/agent/{role}"}


def test_full_flow(server) -> None:
    async def go():
        async with Client(server) as client:
            created = await call(client, "create_kb", kb_id="flujo", title="Flujo de prueba")
            assert created["valid"] is True and created["root_branch"] == "branch-flujo"
            branch = await call(client, "upsert_branch", kb_id="flujo", title="Mecanismos", parent="branch-flujo", summary="Cómo se construye")
            assert branch["id"] == "branch-mecanismos"
            ingested = await call(client, "ingest_text", kb_id="flujo", title="Apunte", text="La interiorización convierte acciones en procesos.\n\nLa encapsulación convierte procesos en objetos.")
            chunk = ingested["chunks"][0]["chunk_id"]
            a = await call(client, "upsert_atom", kb_id="flujo", title="La interiorización convierte acciones en procesos", question="how", answer="Repetir y reflexionar sobre una acción la interioriza en un proceso.", provenance=chunk, tags=["topic:interiorizacion", "system:flujo"], parent=branch["id"])
            b = await call(client, "upsert_atom", kb_id="flujo", title="La encapsulación convierte procesos en objetos", answer="Un proceso concebido como totalidad se encapsula en un objeto.", provenance=chunk, tags=["topic:encapsulacion", "system:flujo"], parent=branch["id"])
            assert a["created"] and b["created"]
            found = await call(client, "search_atoms", kb_id="flujo", query="encapsulación de procesos en objetos", k=2)
            assert found["results"][0]["id"] == b["id"], found
            kids = await call(client, "children", kb_id="flujo", atom_id=branch["id"])
            assert {c["id"] for c in kids["children"]} == {a["id"], b["id"]}
            got = await call(client, "get_atom", kb_id="flujo", atom_id=a["id"])
            assert got["markdown"].startswith("---") and got["provenance"] == chunk
            link = await call(client, "link_atoms", kb_id="flujo", source=b["id"], relation="requires", target=a["id"])
            assert link["type_declared"] is True
            turn = await call(client, "run_turn", kb_id="flujo", question="¿Qué es la encapsulación?", model="test")
            assert turn["reply"] and b["id"] in turn["mesa"]["atom_ids"]
            second = await call(client, "run_turn", kb_id="flujo", question="¿y la interiorización?", conversation_id=turn["conversation_id"])
            assert second["turn"] == 2 and second["conversation_id"] == turn["conversation_id"]
            mesa = await call(client, "inspect_context", kb_id="flujo", question="¿Qué es la interiorización?")
            assert a["id"] in mesa["atom_ids"] and "reasoning_log" in mesa
            bench = await call(client, "benchmark_tutor", kb_id="flujo", k=2, questions=[{"question": "¿Qué es la encapsulación?", "expected_atom_ids": [b["id"]]}])
            assert bench["methods"]["embed"]["metrics"]["hit@1"] == 1.0 and bench["methods"]["mesa"]["metrics"]["mrr"] > 0
            tutors = await call(client, "list_tutors", kb_id="flujo")
            assert [t["role"] for t in tutors["tutors"]] == ["tutor"]
            agent = await call(client, "upsert_tutor", kb_id="flujo", role="tutor", framing="Eres un tutor paciente.", instructions="Cita siempre.")
            assert agent["framing"] == "Eres un tutor paciente."
            stats = await call(client, "kb_stats", kb_id="flujo")
            assert stats["n_atoms"] == 2 and stats["sources"][0]["source_id"] == ingested["source_id"]
            valid = await call(client, "validate_kb", kb_id="flujo")
            assert valid["ok"] is True, valid
            deleted = await call(client, "delete_atom", kb_id="flujo", atom_id=a["id"])
            assert deleted["deleted"] == a["id"]
            assert (await call(client, "validate_kb", kb_id="flujo"))["ok"] is True
            listed = await call(client, "list_kbs")
            assert "flujo" in {k["kb_id"] for k in listed["kbs"]}
            # recursos y prompts
            atom_md = (await client.read_resource(f"tutor://flujo/atom/{b['id']}")).contents[0]
            assert getattr(atom_md, "text", "").startswith("---\nid: " + b["id"])
            agent_md = (await client.read_resource("tutor://flujo/agent/tutor")).contents[0]
            assert "Eres un tutor paciente." in getattr(agent_md, "text", "")
            prompt = await client.get_prompt("author_kb", {"kb_id": "flujo"})
            text = getattr(prompt.messages[0].content, "text", "")
            assert "ingest_text" in text and "upsert_atom" in text and "validate_kb" in text
            session = await client.get_prompt("tutor_session", {"kb_id": "flujo", "role": "tutor"})
            assert "Eres un tutor paciente." in getattr(session.messages[0].content, "text", "")

    run(go())


def test_errors_are_dicts_not_tracebacks(server) -> None:
    async def go():
        async with Client(server) as client:
            missing = await call(client, "kb_stats", kb_id="no-existe")
            bad_id = await call(client, "create_kb", kb_id="Mal Id", title="x")
            bad_parent = await call(client, "upsert_atom", kb_id="flujo", title="x", answer="a", provenance="p", parent="branch-nope")
            bad_chunk = await call(client, "get_chunk", kb_id="flujo", chunk_id="nada")
            return missing, bad_id, bad_parent, bad_chunk

    for result in run(go()):
        assert set(result) == {"error", "hint"}, result
        assert "Traceback" not in result["error"]


def test_selftest_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert mcp_server.selftest(tmp_path) == 0
    out = capsys.readouterr().out
    assert "FAIL" not in out and "selftest: OK" in out
    assert "run_turn" in out and "validate_kb" in out


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_http_requires_bearer_token(tmp_path: Path) -> None:
    port = _free_port()
    env = {**os.environ, "TUTOR_MCP_TOKEN": "secreto", "PYTHONPATH": os.pathsep.join(sys.path), "PYDANTIC_AI_NO_BANNER": "1"}
    process = subprocess.Popen(
        [sys.executable, "-m", "tutor.mcp_server", "--http", f"127.0.0.1:{port}", "--kbs-root", str(tmp_path)],
        env=env, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    url = f"http://127.0.0.1:{port}/mcp"
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    initialize = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}}
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                unauthorized = httpx.post(url, json=initialize, headers=headers, timeout=2)
                break
            except httpx.HTTPError:
                assert process.poll() is None, process.stdout.read()  # type: ignore[union-attr]
                time.sleep(0.2)
        else:
            pytest.fail("el servidor HTTP no levantó")
        assert unauthorized.status_code == 401 and unauthorized.json()["error"] == "unauthorized"
        wrong = httpx.post(url, json=initialize, headers={**headers, "Authorization": "Bearer otro"}, timeout=5)
        assert wrong.status_code == 401
        ok = httpx.post(url, json=initialize, headers={**headers, "Authorization": "Bearer secreto"}, timeout=10)
        assert ok.status_code == 200, ok.text
        body = ok.text
        payload = json.loads(body.split("data: ", 1)[1].splitlines()[0]) if body.startswith("event:") or "data: " in body else ok.json()
        assert payload["result"]["serverInfo"]["name"] == "tutor"
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
