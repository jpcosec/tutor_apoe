"""UI web: contrato de /api/* con el agente nuevo y modelo `test` (sin red)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tutor.web import create_app

ATOM = "atom-action-is-a-core-mental-structure-in-apos"


@pytest.fixture()
def client(kb_root, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("TUTOR_EMBEDDER", "hash")
    return TestClient(create_app(kb_root, model="test"))


def test_index_and_health(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200 and "<html" in res.text.lower()
    health = client.get("/api/health").json()
    assert health["ok"] and health["model"] == "test" and health["n_atoms"] > 0


def test_chat_two_turns(client: TestClient) -> None:
    first = client.post("/api/chat", json={"message": "¿qué es un esquema en APOS?"}).json()
    turn = first["turn"]
    assert turn["assistant_message"] and turn["turn_id"] == "turn-001"
    assert len(turn["mesa"]["items"]) >= 1
    assert {"atom_id", "title", "score", "role", "why"} <= set(turn["mesa"]["items"][0])
    cid, uid = first["conversation_id"], first["user_id"]
    second = client.post("/api/chat", json={"message": "¿y la acción?", "conversation_id": cid, "user_id": uid}).json()
    assert second["turn"]["turn_id"] == "turn-002"
    conv = client.get(f"/api/conversation/{cid}").json()
    assert [t["turn_id"] for t in conv["turns"]] == ["turn-001", "turn-002"]
    listed = client.get(f"/api/user/{uid}/conversations").json()["conversations"]
    assert listed[0]["conversation_id"] == cid and listed[0]["turn_count"] == 2
    assert client.get(f"/api/turn/{cid}/turn-002").status_code == 200
    assert client.get(f"/api/turn/{cid}/turn-009").status_code == 404
    assert client.get("/api/conversation/nope").status_code == 404


def test_atom(client: TestClient) -> None:
    assert client.get(f"/api/atom/{ATOM}").status_code == 200
    assert client.get("/api/atom/nope").status_code == 404


# -- grafo --------------------------------------------------------------------------------

BRANCH = "branch-apos-core-structures-action"


def test_graph_page(client: TestClient) -> None:
    res = client.get("/graph")
    assert res.status_code == 200 and "<html" in res.text.lower()
    assert client.get("/graph/static/mindmap.js").status_code == 200
    assert "/graph" in client.get("/").text


def test_graph_nodes(client: TestClient) -> None:
    nodes = client.get("/api/graph").json()["atoms"]
    assert len(nodes) >= 140
    kinds = {n["node_type"] for n in nodes}
    assert {"branch", "knowledge"} <= kinds
    by_id = {n["id"]: n for n in nodes}
    assert {"id", "title", "tags", "answer", "provenance", "question", "parent_id"} <= set(nodes[0])
    kids = [n for n in nodes if n["parent_id"] == BRANCH]
    assert kids
    assert by_id[BRANCH]["node_type"] == "branch"
    assert all(n["parent_id"] in by_id for n in nodes if n["parent_id"])


def test_search(client: TestClient) -> None:
    found = client.get("/api/search", params={"q": "encapsulación"}).json()["atoms"]
    assert found and any("encapsulaci" in " ".join(n["tags"]) + n["title"].lower() for n in found)
    assert len(client.get("/api/search").json()["atoms"]) >= 140


@pytest.fixture()
def tmp_client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from tutor import authoring

    monkeypatch.setenv("TUTOR_EMBEDDER", "hash")
    authoring.create_kb("demo", "Demo", root=tmp_path)
    authoring.upsert_atom("demo", {"id": "atom-uno", "title": "Uno", "question": "what", "answer": "Uno es uno.", "provenance": "test", "parent": "branch-demo"}, tmp_path)
    return TestClient(create_app(tmp_path / "demo", model="test"))


def test_edit_and_add_child(tmp_client: TestClient) -> None:
    nodes = {n["id"]: n for n in tmp_client.get("/api/graph").json()["atoms"]}
    assert nodes["atom-uno"]["parent_id"] == "branch-demo"
    body = {**nodes["atom-uno"], "title": "Uno editado"}
    res = tmp_client.post("/api/atoms/atom-uno", json=body)
    assert res.status_code == 200 and res.json()["atom"]["title"] == "Uno editado"
    after = {n["id"]: n for n in tmp_client.get("/api/graph").json()["atoms"]}
    assert after["atom-uno"]["title"] == "Uno editado"
    child = tmp_client.post("/api/atoms/branch-demo/children", json={"title": "Hijo nuevo", "node_type": "knowledge"})
    assert child.status_code == 200 and child.json()["atom"]["parent_id"] == "branch-demo"
    sub = tmp_client.post("/api/atoms/branch-demo/children", json={"title": "Rama nueva", "node_type": "branch"}).json()["atom"]
    assert sub["node_type"] == "branch"
    assert tmp_client.post("/api/atoms/nope", json={"title": "x"}).status_code == 404
