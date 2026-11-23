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
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tutor import authoring, modules, wiki, world
from tutor.agent import Conversation, TurnResult
from tutor.surface import SurfaceView

STATIC = Path(__file__).parent / "static"
INDEX = STATIC / "index.html"
GRAPH = STATIC / "graph"
SURFACE = STATIC / "surface"
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
            "citation": item.get("citation") or "",
            "surface_url": item.get("surface_url"),
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


def graph_node(document: Any) -> dict[str, Any]:
    """Documento sldb -> nodo con la forma que espera `graph/mindmap.js`."""
    flat = world.atom_dict(document)
    branch = document.model == world.BRANCH_MODEL
    node = {
        "id": flat["id"],
        "title": flat["title"],
        "question": flat["question"] or ("branch" if branch else "what"),
        "tags": list(flat["tags"]),
        "answer": flat["summary"] or "",
        "provenance": flat["provenance"] or "",
        "citation": flat.get("citation") or flat["provenance"] or "",
        "provenance_refs": flat.get("provenance_refs") or [],
        "surface_url": flat.get("surface_url"),
        "coverage": flat.get("coverage"),
        "node_type": "branch" if branch else "knowledge",
        "model": flat["model"],
        "parent_id": flat["parent"],
        "path": flat["path"],
    }
    status = document.payload.get("status")
    if status:
        node["status"] = status
    return node


def create_app(kb_root: Path | str | None = None, model: str = "test", role: str = "tutor", host: str = "127.0.0.1") -> FastAPI:
    """`host` es la interfaz en que escuchará el servidor: decide si la wiki de configuración se abre
    sin clave (solo en loopback). `app.state.wiki` lo pone quien lanza el `sldb serve` (`tutor web`)."""
    root = Path(kb_root) if kb_root else world.kb_root_default()
    kb = world.open_kb(root)
    doc = world.agent(kb, role) or {}
    app_name = str(doc.get("title") or DEFAULT_NAME)
    
    app = FastAPI(title=app_name)
    app.state.kb = kb
    app.state.kb_root = root.resolve()
    app.state.wiki = wiki.Backend()
    app.state.modules = modules.Backend()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    lock = Lock()
    chats: dict[str, Conversation] = {}
    conversations: dict[str, dict[str, Any]] = {}
    users: dict[str, list[str]] = {}

    def summary(conv: dict[str, Any]) -> dict[str, Any]:
        return {**{k: v for k, v in conv.items() if k != "turns"}, "turn_count": len(conv["turns"])}

    app.mount("/graph/static", StaticFiles(directory=GRAPH), name="graph-static")
    app.mount("/surface/static", StaticFiles(directory=SURFACE), name="surface-static")
    surfaces: dict[str, SurfaceView] = {}

    def surface_view() -> SurfaceView:
        current = app.state.kb
        key = str(getattr(current, "fingerprint", id(current)))
        if key not in surfaces:
            surfaces.clear()
            surfaces[key] = SurfaceView(current)
        return surfaces[key]

    @app.get("/")
    def index():
        return FileResponse(INDEX.with_name("app.html"), media_type="text/html")

    @app.get("/chat")
    def chat_view(embed: bool = False):
        if not embed:
            return RedirectResponse("/#chat")
        return FileResponse(INDEX, media_type="text/html")

    @app.get("/scratch")
    def scratch_view(embed: bool = False):
        if not embed:
            return RedirectResponse("/#scratch")
        return FileResponse(INDEX.with_name("scratch.html"), media_type="text/html")

    @app.get("/ui/navigation.js")
    def navigation_script():
        return FileResponse(INDEX.with_name("navigation.js"), media_type="text/javascript")

    @app.get("/graph")
    def graph_page():
        return FileResponse(GRAPH / "index.html", media_type="text/html")

    @app.get("/surface")
    def surface_page():
        return FileResponse(SURFACE / "index.html", media_type="text/html")

    @app.get("/api/surface/outline")
    def surface_outline():
        return surface_view().outline()

    @app.get("/api/surface/page/{number}")
    def surface_page_data(number: int):
        found = surface_view().page(number)
        if found is None:
            raise HTTPException(status_code=404, detail="page not found")
        return found

    @app.get("/api/surface/atom/{atom_id}")
    def surface_atom(atom_id: str):
        found = surface_view().atom(atom_id)
        if found is None:
            raise HTTPException(status_code=404, detail="atom not found")
        return found

    @app.get("/api/surface/chunk/{chunk_id}")
    def surface_chunk(chunk_id: str):
        found = surface_view().chunk(chunk_id)
        if found is None:
            raise HTTPException(status_code=404, detail="chunk not found")
        return found

    def all_nodes() -> list[dict[str, Any]]:
        current = app.state.kb
        docs = [*current.by_model(world.BRANCH_MODEL), *current.by_model(world.KNOWLEDGE_MODEL)]
        return [graph_node(d) for d in docs]

    @app.get("/api/graph")
    def graph():
        return {"atoms": all_nodes()}

    @app.get("/api/search")
    def search(q: str = "", k: int = 60):
        q = q.strip()
        nodes = all_nodes()
        if not q:
            return {"atoms": nodes}
        by_id = {n["id"]: n for n in nodes}
        if ":" in q and " " not in q:  # filtro por tag exacto, p.ej. topic:schema
            return {"atoms": [n for n in nodes if q in n["tags"]]}
        hits = world.rank(app.state.kb, q, k)
        return {"atoms": [by_id[i] for i, _ in hits if i in by_id]}

    def write_node(node_id: str | None, body: dict[str, Any], *, branch: bool, parent: str | None) -> dict[str, Any]:
        data: dict[str, Any] = {"title": body.get("title"), "parent": parent, "tags": body.get("tags") or None}
        if node_id:
            data["id"] = node_id
        kb_id = app.state.kb_root.name
        base = app.state.kb_root.parent
        try:
            with lock:
                if branch:
                    data["summary"] = body.get("answer") or ""
                    if body.get("provenance"):
                        data["provenance"] = body["provenance"]
                    if not data["tags"]:
                        data.pop("tags")
                    authoring.upsert_branch(kb_id, data, base)
                else:
                    data.update(
                        question=body.get("question") or "what",
                        answer=body.get("answer") or body.get("title"),
                        provenance=body.get("provenance") or "Creado desde el visor de grafo.",
                    )
                    authoring.upsert_atom(kb_id, data, base)
                app.state.kb = world.open_kb(app.state.kb_root)
        except authoring.AuthoringError as exc:
            raise HTTPException(status_code=400, detail=f"{exc}") from exc
        new_id = data.get("id") or None
        found = next((n for n in all_nodes() if n["id"] == (new_id or "")), None)
        if found is None:  # id derivado del título
            found = next((n for n in all_nodes() if n["title"] == body.get("title")), None)
        return {"atom": found}

    @app.post("/api/atoms/{node_id}")
    def update_atom(node_id: str, body: dict[str, Any]):
        document = next((d for d in app.state.kb.by_model(world.BRANCH_MODEL) if d.name == node_id), None)
        if document is None and world.get_atom(app.state.kb, node_id) is None:
            raise HTTPException(status_code=404, detail="atom not found")
        return write_node(node_id, body, branch=document is not None, parent=body.get("parent_id") or body.get("parent"))

    @app.post("/api/atoms/{node_id}/children")
    def add_child(node_id: str, body: dict[str, Any]):
        if world.get_atom(app.state.kb, node_id) is None:
            raise HTTPException(status_code=404, detail="parent not found")
        if not str(body.get("title") or "").strip():
            raise HTTPException(status_code=400, detail="title requerido")
        return write_node(None, body, branch=body.get("node_type") == "branch", parent=node_id)

    @app.get("/api/health")
    def health():
        return {"ok": True, "kb": app.state.kb.name, "model": model, "n_atoms": len(world.list_atoms(app.state.kb)), "app_name": app_name}

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
                chats[conversation_id] = Conversation(kb=app.state.kb, model=model, role=role)
            chats[conversation_id].kb = app.state.kb  # la KB vigente: lo guardado en la wiki o el grafo vale desde este turno
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
        found = world.get_atom(app.state.kb, atom_id)
        if not found:
            raise HTTPException(status_code=404, detail="atom not found")
        return found

    def page_model(name: str) -> str | None:
        try:
            document = app.state.kb.get(name)
        except KeyError:
            return None
        return document.model if document.name == name else None

    def reopen_kb() -> str | None:
        """Tras un guardado por la wiki: la `KnowledgeBase` en memoria no ve lo escrito por `sldb serve`,
        así que se vuelve a abrir. Devuelve por qué el tutor no podría seguir con lo guardado, si es el caso."""
        wiki.forget_store_reads(app.state.kb_root / world.STORE_DIR)
        try:
            fresh = world.open_kb(app.state.kb_root, build_if_missing=False)
        except Exception as error:  # la KB dejó de validar: se informa y se deshace el guardado
            errors = [e.line() for e in getattr(getattr(error, "report", None), "errors", [])] or [str(error).strip() or type(error).__name__]
            return f"la base deja de validar ({'; '.join(errors[:3])})."
        if world.agent(fresh, role) is None:
            return f"el rol «{role}» se queda sin su página de configuración."
        with lock:
            app.state.kb = fresh
        return None

    app.include_router(wiki.router(lambda: app.state.wiki, host=host, model_of=page_model, after_save=reopen_kb))
    app.include_router(modules.router(lambda: app.state.modules, host=host))

    from tutor.preload_web import router

    app.include_router(router(model))
    from tutor.graph_web import router as graph_router

    app.include_router(graph_router())
    return app
