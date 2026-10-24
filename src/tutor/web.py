"""UI web del tutor: FastAPI con el contrato de la UI vieja (`/api/chat`, `/api/conversation/...`).

    tutor web --kb kbs/apos --model test --port 8300

Conversaciones y usuarios viven en memoria; cada conversación tiene su `Conversation` del agente nuevo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from tutor import world
from tutor.agent import Conversation, TurnResult

INDEX = Path(__file__).parent / "static" / "index.html"
DEFAULT_NAME = "Tutor APOS"


class ChatRequest(BaseModel):
    message: str
    user_id: str | None = None
    conversation_id: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def adapt_mesa(mesa: dict[str, Any], turn_index: int) -> dict[str, Any]:
    """Mesa nueva -> forma que espera la UI (items, listas retained/removed/added, reasoning_*)."""
    items = [
        {
            "atom_id": item.get("atom_id"),
            "title": item.get("title") or item.get("atom_id"),
            "score": item.get("score", 0.0),
            "role": item.get("role") or "",
            "why": item.get("why") or "",
            "tags": list(item.get("tags") or []),
        }
        for item in mesa.get("items", [])
    ]
    tags = sorted({tag for item in items for tag in item["tags"]})
    return {
        **mesa,
        "mesa_id": f"mesa-{turn_index:03d}",
        "atom_ids": list(mesa.get("atom_ids") or [item["atom_id"] for item in items]),
        "items": items,
        "include_tags": list(mesa.get("include_tags") or tags),
        "retained_atom_ids": list(mesa.get("retained_atom_ids") or []),
        "removed_atom_ids": list(mesa.get("removed_atom_ids") or []),
        "added_atom_ids": list(mesa.get("added_atom_ids") or []),
        "reasoning_summary": [str(x) for x in mesa.get("reasoning_summary") or []],
        "reasoning_log": list(mesa.get("reasoning_log") or []),
    }


def create_app(kb_root: Path | str | None = None, model: str = "test", role: str = "tutor") -> FastAPI:
    kb = world.open_kb(Path(kb_root) if kb_root else None)
    doc = world.agent(kb, role) or {}
    app_name = str(doc.get("title") or DEFAULT_NAME)
    n_atoms = len(world.list_atoms(kb))

    app = FastAPI(title=app_name)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    lock = Lock()
    chats: dict[str, Conversation] = {}
    conversations: dict[str, dict[str, Any]] = {}
    users: dict[str, list[str]] = {}

    def summary(conv: dict[str, Any]) -> dict[str, Any]:
        return {**{k: v for k, v in conv.items() if k != "turns"}, "turn_count": len(conv["turns"])}

    @app.get("/")
    def index():
        return FileResponse(INDEX, media_type="text/html")

    @app.get("/api/health")
    def health():
        return {"ok": True, "kb": kb.name, "model": model, "n_atoms": n_atoms, "app_name": app_name}

    @app.post("/api/chat")
    def chat(req: ChatRequest):
        user_id = req.user_id or f"user-{uuid4()}"
        conversation_id = req.conversation_id or f"conv-{uuid4()}"
        with lock:
            users.setdefault(user_id, [])
            conv = conversations.get(conversation_id)
            if conv is None:
                now = _now()
                conv = conversations[conversation_id] = {
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "created_at": now,
                    "updated_at": now,
                    "title": req.message[:80],
                    "metadata": {},
                    "turns": [],
                }
                users[user_id].append(conversation_id)
                chats[conversation_id] = Conversation(kb=kb, model=model, role=role)
            result: TurnResult = chats[conversation_id].ask(req.message)
            index_ = len(conv["turns"]) + 1
            turn = {
                "turn_id": f"turn-{index_:03d}",
                "conversation_id": conversation_id,
                "user_id": user_id,
                "turn_index": index_,
                "user_message": req.message,
                "assistant_message": result.reply,
                "mesa": adapt_mesa(result.mesa, index_),
                "created_at": _now(),
            }
            conv["turns"].append(turn)
            conv["updated_at"] = turn["created_at"]
        return {"user_id": user_id, "conversation_id": conversation_id, "turn": turn}

    @app.get("/api/conversation/{conversation_id}")
    def conversation_detail(conversation_id: str):
        conv = conversations.get(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="conversation not found")
        return conv

    @app.get("/api/user/{user_id}/conversations")
    def user_conversations(user_id: str):
        convs = [summary(conversations[c]) for c in users.get(user_id, [])]
        convs.sort(key=lambda c: c["updated_at"], reverse=True)
        return {"user_id": user_id, "conversations": convs}

    @app.get("/api/turn/{conversation_id}/{turn_id}")
    def turn_detail(conversation_id: str, turn_id: str):
        conv = conversations.get(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="conversation not found")
        for turn in conv["turns"]:
            if turn["turn_id"] == turn_id:
                return turn
        raise HTTPException(status_code=404, detail="turn not found")

    @app.get("/api/atom/{atom_id}")
    def atom(atom_id: str):
        found = world.get_atom(kb, atom_id)
        if not found:
            raise HTTPException(status_code=404, detail="atom not found")
        return found

    return app
