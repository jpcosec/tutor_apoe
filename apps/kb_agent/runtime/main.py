from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / '.env')
load_dotenv(Path('/home/jp/proyectos/gemini_test/.env'))

from .compiler import MesaCompiler
from .pack_loader import KnowledgePack, load_pack
from .responder import GeminiResponder
from .storage import Storage

pack = load_pack()
compiler = MesaCompiler(pack)
storage = Storage(pack.pack_id)
responder = GeminiResponder(pack)


class ChatRequest(BaseModel):
    message: str
    user_id: str | None = None
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    user_id: str
    conversation_id: str
    turn: dict


def build_prompt(message: str, prompt_mesa: dict, knowledge_pack: KnowledgePack) -> str:
    mesa_json = json.dumps(prompt_mesa, ensure_ascii=False, indent=2)
    return f"""
{knowledge_pack.prompt_policy}

Pregunta del usuario:
{message}

CONTEXTO:
{mesa_json}
""".strip()


def create_app() -> FastAPI:
    application = FastAPI(title='KB Chat UI')
    application.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    @application.on_event('startup')
    def startup() -> None:
        storage.init_db()

    @application.get('/')
    def index():
        return FileResponse(pack.index_path)

    @application.post('/api/chat', response_model=ChatResponse)
    def chat(req: ChatRequest):
        user_id = req.user_id or f'user-{uuid4()}'
        conversation_id = req.conversation_id or f'conv-{uuid4()}'

        storage.ensure_user(user_id)
        storage.ensure_conversation(conversation_id, user_id, title=req.message[:80])

        turns = storage.get_conversation_turns(conversation_id)
        previous_turn = turns[-1] if turns else None
        compiled = compiler.compile(req.message, previous_turn=previous_turn)
        prompt = build_prompt(req.message, compiled['prompt_mesa'], pack)
        reply = responder.generate(prompt)

        turn_id = f"turn-{len(turns) + 1:03d}"
        turn = storage.save_turn(
            conversation_id=conversation_id,
            user_id=user_id,
            turn_id=turn_id,
            user_message=req.message,
            assistant_message=reply,
            mesa=compiled['mesa'],
        )
        return ChatResponse(user_id=user_id, conversation_id=conversation_id, turn=turn)

    @application.get('/api/conversation/{conversation_id}')
    def conversation_detail(conversation_id: str):
        conversation = storage.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail='conversation not found')
        return conversation

    @application.get('/api/user/{user_id}/conversations')
    def user_conversations(user_id: str):
        return {'user_id': user_id, 'conversations': storage.get_user_conversations(user_id)}

    @application.get('/api/turn/{conversation_id}/{turn_id}')
    def turn_detail(conversation_id: str, turn_id: str):
        conversation = storage.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail='conversation not found')
        for turn in conversation['turns']:
            if turn['turn_id'] == turn_id:
                return turn
        raise HTTPException(status_code=404, detail='turn not found')

    @application.get('/api/atom/{atom_id}')
    def atom(atom_id: str):
        for atom_item in pack.atoms_data.get('atoms', []):
            if atom_item.get('id') == atom_id:
                return atom_item
        raise HTTPException(status_code=404, detail='atom not found')

    application.mount('/static', StaticFiles(directory=pack.base_dir), name='static')
    return application


app = create_app()
