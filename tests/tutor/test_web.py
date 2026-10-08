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
