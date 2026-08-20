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
from google import genai
from pydantic import BaseModel

BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / '.env')
load_dotenv(Path('/home/jp/proyectos/gemini_test/.env'))

from storage import ensure_conversation, ensure_user, get_conversation, get_conversation_turns, get_user_conversations, init_db, save_turn
from table_compiler import MesaCompiler

ATOMS_JSON = BASE_DIR / 'atoms.json'

app = FastAPI(title='KB Chat UI')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

client = genai.Client()
compiler = MesaCompiler()
_atoms_cache: dict | None = None


class ChatRequest(BaseModel):
    message: str
    user_id: str | None = None
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    user_id: str
    conversation_id: str
    turn: dict


@app.on_event('startup')
def startup() -> None:
    init_db()


def load_atoms() -> dict:
    global _atoms_cache
    if _atoms_cache is None:
        _atoms_cache = json.loads(ATOMS_JSON.read_text(encoding='utf-8'))
    return _atoms_cache


def build_prompt(message: str, prompt_mesa: dict) -> str:
    mesa_json = json.dumps(prompt_mesa, ensure_ascii=False, indent=2)
    return f"""
Responde en español usando SOLO la información incluida abajo.

Reglas:
- No inventes nada fuera de los items provistos.
- Sé concreto.
- Máximo 140 palabras.
- Máximo 5 bullets.
- Conserva los ids atom-... en el texto cuando cites evidencia.
- Si la información no alcanza, dilo en una línea.

Pregunta del usuario:
{message}

CONTEXTO:
{mesa_json}
""".strip()


@app.get('/')
def index():
    return FileResponse(BASE_DIR / 'index.html')


@app.post('/api/chat', response_model=ChatResponse)
def chat(req: ChatRequest):
    user_id = req.user_id or f'user-{uuid4()}'
    conversation_id = req.conversation_id or f'conv-{uuid4()}'

    ensure_user(user_id)
    ensure_conversation(conversation_id, user_id, title=req.message[:80])

    turns = get_conversation_turns(conversation_id)
    previous_turn = turns[-1] if turns else None
    compiled = compiler.compile(req.message, previous_turn=previous_turn)
    prompt = build_prompt(req.message, compiled['prompt_mesa'])
    response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
    reply = (response.text or '').strip()

    turn_id = f"turn-{len(turns) + 1:03d}"
    turn = save_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        turn_id=turn_id,
        user_message=req.message,
        assistant_message=reply,
        mesa=compiled['mesa'],
    )
    return ChatResponse(user_id=user_id, conversation_id=conversation_id, turn=turn)


@app.get('/api/conversation/{conversation_id}')
def conversation_detail(conversation_id: str):
    conversation = get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail='conversation not found')
    return conversation


@app.get('/api/user/{user_id}/conversations')
def user_conversations(user_id: str):
    return {'user_id': user_id, 'conversations': get_user_conversations(user_id)}


@app.get('/api/turn/{conversation_id}/{turn_id}')
def turn_detail(conversation_id: str, turn_id: str):
    conversation = get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail='conversation not found')
    for turn in conversation['turns']:
        if turn['turn_id'] == turn_id:
            return turn
    raise HTTPException(status_code=404, detail='turn not found')


@app.get('/api/atom/{atom_id}')
def atom(atom_id: str):
    data = load_atoms()
    for atom in data.get('atoms', []):
        if atom.get('id') == atom_id:
            return atom
    raise HTTPException(status_code=404, detail='atom not found')


app.mount('/static', StaticFiles(directory=BASE_DIR), name='static')
