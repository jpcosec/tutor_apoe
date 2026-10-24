"""Servidor MCP del tutor: crear y poblar KBs sldb desde el chat (o desde ingesta) y levantar y
probar tutores sobre ellas. Es el único módulo que importa la SDK de MCP; la lógica vive en
`tutor.authoring` (escritura), `tutor.ingest` (fuentes), `tutor.world` (lectura) y `tutor.agent`
(turnos).

    tutor-mcp                              # stdio (Claude Desktop, Claude Code, …)
    tutor-mcp --http 0.0.0.0:8200          # streamable HTTP en /mcp; Bearer obligatorio si TUTOR_MCP_TOKEN
    tutor-mcp --kbs-root /datos/kbs        # dónde viven las KBs (default TUTOR_KBS_ROOT o kbs/)
    tutor-mcp --selftest                   # crea una KB temporal y recorre todas las tools; exit 0

Las tools nunca devuelven un traceback: ante un error de uso responden `{error, hint}`.
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import logging
import os
import re
import sys
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from tutor import authoring, ingest, world
from tutor.authoring import AuthoringError

log = logging.getLogger("tutor.mcp")

ENV_MODEL = "TUTOR_MODEL"
ENV_TOKEN = "TUTOR_MCP_TOKEN"
DEFAULT_MODEL = "test"
HTTP_PATH = "/mcp"
SERVER_NAME = "tutor"
#: Palabras vacías del español que no cuentan como coincidencia léxica en `search_atoms`.
STOPWORDS = frozenset(
    "que cual cuales quien quienes como cuando donde por para con sin sobre entre una uno unos unas los las del "
    "the and ser son esta este estas estos esa ese eso hay tiene puede mas muy pero porque".split()
)

INSTRUCTIONS = """\
tutor: KBs de conocimiento atómico (sldb) y tutores que responden citando sus átomos.

Cómo trabajar:
1. `list_kbs` para ver qué hay; `create_kb` para empezar una (nace válida, con rama raíz
   `branch-<kb_id>` y un rol `tutor`).
2. Para poblar desde una fuente: `ingest_text`/`ingest_file` devuelve fragmentos con `chunk_id`;
   lee cada fragmento y propone átomos (una afirmación por átomo, pregunta 5W1H, tags
   `namespace:valor`, `provenance` = el `chunk_id`) con `upsert_atom`. Agrupa con `upsert_branch`.
3. `validate_kb` después de cada tanda: debe dar `ok: true`.
4. Prueba el tutor: `inspect_context` muestra qué átomos vería (sin LLM); `run_turn` responde
   (con `model="test"` no gasta nada); `benchmark_tutor` mide hit@k/MRR sobre preguntas esperadas.
Los recursos `tutor://<kb_id>/atom/<id>` y `tutor://<kb_id>/agent/<rol>` dan el markdown tal cual.
El prompt `author_kb` trae la guía completa de autoría; `tutor_session` el encuadre para conversar.
"""


class BenchmarkQuestion(BaseModel):
    """Una pregunta del benchmark y los átomos que deberían salir."""

    question: str = Field(description="La pregunta tal como la haría un estudiante.")
    expected_atom_ids: list[str] = Field(description="Ids de átomos que cuentan como acierto.")
    id: str | None = Field(default=None, description="Etiqueta opcional de la pregunta.")


@dataclass
class ServerState:
    """Lo que el servidor recuerda entre llamadas: la raíz, las KBs abiertas y las conversaciones."""

    root: Path | None = None
    kbs: dict[str, Any] = field(default_factory=dict)
    conversations: dict[str, Any] = field(default_factory=dict)

    def kb(self, kb_id: str):
        """La KB abierta (validada) y cacheada hasta la próxima escritura sobre ella."""
        if kb_id not in self.kbs:
            path = authoring.kb_path(kb_id, self.root)
            try:
                self.kbs[kb_id] = world.open_kb(path, build_if_missing=False)
            except Exception as error:
                hint = "corre validate_kb para ver los errores y rebuild_kb si falta el store"
                raise AuthoringError(f"la KB {kb_id!r} no abre: {_first_line(error)}", hint) from error
        return self.kbs[kb_id]

    def touched(self, kb_id: str) -> None:
        self.kbs.pop(kb_id, None)


def _first_line(error: BaseException) -> str:
    text = str(error).strip()
    report = getattr(error, "report", None)
    if report is not None and getattr(report, "errors", None):
        text = "; ".join(e.line() for e in report.errors[:3])
    return text.splitlines()[0] if text else type(error).__name__


def _safe(func: Callable[..., Any]) -> Callable[..., dict[str, Any]]:
    """Nunca un traceback al cliente: `{error, hint}` ante cualquier excepción."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return func(*args, **kwargs)
        except AuthoringError as error:
            return error.to_dict()
        except Exception as error:  # noqa: BLE001 — el cliente es un LLM: mensaje y pista, no stack
            log.exception("tool %s falló", func.__name__)
            return {"error": f"{type(error).__name__}: {_first_line(error)}", "hint": "revisa los argumentos; si persiste, mira el log del servidor"}

    return wrapper


def default_model() -> str:
    return os.environ.get(ENV_MODEL) or DEFAULT_MODEL


def tool_result(result: Any) -> dict[str, Any]:
    """El dict que devolvió una tool, desde un `CallToolResult` (estructurado o texto JSON)."""
    data = getattr(result, "structured_content", None)
    if data is None:
        data = json.loads(result.content[0].text)
    if isinstance(data, dict) and set(data) == {"result"}:
        data = data["result"]
    return data


# --------------------------------------------------------------------------------------------
# El servidor
# --------------------------------------------------------------------------------------------


def build(kbs_root: Path | str | None = None) -> MCPServer:
    """El `MCPServer` con todas las tools, recursos y prompts sobre `kbs_root`."""
    state = ServerState(root=Path(kbs_root).expanduser().resolve() if kbs_root else None)
    server = MCPServer(SERVER_NAME, instructions=INSTRUCTIONS)
    read_only = ToolAnnotations(read_only_hint=True, open_world_hint=False)
    writes = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
    destructive = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)
    calls_model = ToolAnnotations(read_only_hint=True, open_world_hint=True)
    root = state.root

    # -- KBs --------------------------------------------------------------------------

    @server.tool(annotations=read_only)
    @_safe
    def list_kbs() -> dict[str, Any]:
        """Las KBs disponibles bajo la raíz del servidor (TUTOR_KBS_ROOT): id, ruta, cuántos átomos y
        ramas, roles de tutor declarados y si validan."""
        return {"root": str(authoring.kbs_root(root)), "kbs": authoring.list_kbs(root)}

    @server.tool(annotations=writes)
    @_safe
    def create_kb(kb_id: str, title: str, language: str = "es", description: str = "") -> dict[str, Any]:
        """Crea una KB nueva y válida: `kb.yaml`, categorías de tags por defecto (system, topic, layer,
        node, agent), relación `child_of`, rama raíz `branch-<kb_id>`, y un tutor (`agent-tutor-<kb_id>`)
        con encuadre e instrucciones por defecto que luego puedes afinar con `upsert_tutor`.
        `kb_id`: minúsculas, dígitos y guiones, empezando por letra."""
        state.touched(kb_id)
        return authoring.create_kb(kb_id, title, language, description, root=root)

    @server.tool(annotations=read_only)
    @_safe
    def validate_kb(kb_id: str) -> dict[str, Any]:
        """La validación real del runtime (reglas V0–V13 de `kb`): `{ok, errors, warnings, stats}`.
        Úsala después de cada tanda de cambios; `ok` debe ser true antes de probar el tutor."""
        return authoring.validate_kb(kb_id, root)

    @server.tool(annotations=writes)
    @_safe
    def rebuild_kb(kb_id: str) -> dict[str, Any]:
        """Reconstruye desde cero el store sldb y el índice de embeddings a partir de los `.md` de la
        KB. Úsala si la KB se movió de máquina, si `validate_kb` acusa el store, o tras editar `.md` a mano."""
        state.touched(kb_id)
        return authoring.rebuild_kb(kb_id, root)

    @server.tool(annotations=read_only)
    @_safe
    def kb_stats(kb_id: str) -> dict[str, Any]:
        """Resumen de una KB: conteos por modelo, relaciones por tipo, ramas de primer nivel, roles,
        fuentes ingeridas y embedder."""
        kb = state.kb(kb_id)
        stats = kb.stats()
        branches = world.list_branches(kb)
        return {
            **authoring.kb_info(kb_id, root),
            "by_model": stats.by_model,
            "top_branches": [{"id": b["id"], "title": b["title"]} for b in branches if b.get("parent") in (None, "")],
            "sources": ingest.list_sources(kb_id, root),
            "fingerprint": kb.fingerprint,
        }

    # -- átomos ---------------------------------------------------------------------------

    @server.tool(annotations=read_only)
    @_safe
    def search_atoms(kb_id: str, query: str, k: int = 8) -> dict[str, Any]:
        """Los `k` átomos más parecidos a `query`: similitud del índice de embeddings más coincidencia
        léxica en título, tags y respuesta. Devuelve id, título, puntaje, por qué y la respuesta recortada."""
        return {"query": query, "results": _search(state.kb(kb_id), query, k)}

    @server.tool(annotations=read_only)
    @_safe
    def get_atom(kb_id: str, atom_id: str) -> dict[str, Any]:
        """Un átomo o rama completo por id: título, pregunta, respuesta, procedencia, tags, padre, hijos y
        relaciones tipadas en que participa."""
        kb = state.kb(kb_id)
        atom = world.get_atom(kb, atom_id)
        if atom is None:
            raise AuthoringError(f"no existe {atom_id!r} en {kb_id!r}", "búscalo con search_atoms o list_branches")
        document = kb.get(atom_id)
        relations = [
            {"type": r.relation_type, "source": r.source_ref.rpartition(":")[2], "target": r.target_ref.rpartition(":")[2]}
            for r in [*kb.outgoing(atom_id), *kb.incoming(atom_id)]
        ]
        return {**atom, "children": [c["id"] for c in world.children(kb, atom_id)], "relations": relations, "markdown": kb.render(document.key)}

    @server.tool(annotations=read_only)
    @_safe
    def list_branches(kb_id: str) -> dict[str, Any]:
        """La taxonomía completa: todas las ramas con id, título, padre y cuántos hijos directos tiene cada una."""
        kb = state.kb(kb_id)
        return {"branches": [{**b, "n_children": len(world.children(kb, b["id"]))} for b in world.list_branches(kb)]}

    @server.tool(annotations=read_only)
    @_safe
    def children(kb_id: str, atom_id: str) -> dict[str, Any]:
        """Los hijos directos de una rama (o átomo) por la relación `child_of`: átomos y subramas."""
        kb = state.kb(kb_id)
        if world.get_atom(kb, atom_id) is None:
            raise AuthoringError(f"no existe {atom_id!r} en {kb_id!r}", "usa list_branches")
        return {"parent": atom_id, "children": world.children(kb, atom_id)}

    @server.tool(annotations=writes)
    @_safe
    def upsert_atom(
        kb_id: str,
        title: str,
        answer: str,
        provenance: str,
        parent: str,
        question: str = "what",
        tags: list[str] | None = None,
        id: str | None = None,
    ) -> dict[str, Any]:
        """Crea o actualiza un átomo de conocimiento. Un átomo afirma UNA sola cosa: `title` es la
        afirmación en corto, `question` la pregunta 5W1H que responde (what, why, how, how_not, when,
        where, for_whom), `answer` la respuesta curada (párrafos; sin encabezados), `provenance` de
        dónde sale (idealmente el `chunk_id` de `ingest_text`), `tags` como `namespace:valor` (p. ej.
        topic:accion, layer:theory; los namespaces nuevos se declaran solos), `parent` una rama existente
        (`branch-<kb_id>` es la raíz). Sin `id` se deriva del título (`atom-<slug>`); con un `id`
        existente, actualiza."""
        state.touched(kb_id)
        atom = {"id": id, "title": title, "question": question, "answer": answer, "provenance": provenance, "tags": tags or [], "parent": parent}
        return authoring.upsert_atom(kb_id, atom, root)

    @server.tool(annotations=writes)
    @_safe
    def upsert_branch(kb_id: str, title: str, parent: str, summary: str = "", id: str | None = None) -> dict[str, Any]:
        """Crea o actualiza una rama de la taxonomía (agrupa átomos y otras ramas). `parent` debe ser una
        rama existente; `summary` dice qué agrupa. Sin `id` se deriva del título (`branch-<slug>`)."""
        state.touched(kb_id)
        return authoring.upsert_branch(kb_id, {"id": id, "title": title, "parent": parent, "summary": summary}, root)

    @server.tool(annotations=destructive)
    @_safe
    def delete_atom(kb_id: str, atom_id: str) -> dict[str, Any]:
        """Borra un átomo (o una rama sin hijos) junto con todas sus relaciones y su vector."""
        state.touched(kb_id)
        return authoring.delete_atom(kb_id, atom_id, root)

    @server.tool(annotations=writes)
    @_safe
    def link_atoms(kb_id: str, source: str, relation: str, target: str, description: str = "") -> dict[str, Any]:
        """Una relación tipada `source --relation--> target` entre dos documentos existentes (p. ej.
        `requires`, `contrasts_with`, `example_of`). Si el tipo no existe se declara con `description`.
        `child_of` mueve el origen bajo el destino en la taxonomía."""
        state.touched(kb_id)
        return authoring.link_atoms(kb_id, source, relation, target, description=description, root=root)

    # -- ingesta -------------------------------------------------------------------------

    @server.tool(annotations=writes)
    @_safe
    def ingest_text(kb_id: str, title: str, text: str, chunk_chars: int = ingest.DEFAULT_CHUNK_CHARS, source_path: str | None = None) -> dict[str, Any]:
        """Guarda un texto como fuente de la KB y lo parte en fragmentos (`chunk_id`) de hasta `chunk_chars`
        caracteres, por párrafos. No llama a ningún LLM: devuelve los fragmentos para que TÚ propongas
        átomos con `upsert_atom` citando el `chunk_id` en `provenance`. Los fragmentos no entran al índice
        ni los ve el tutor. Mismo título = reemplaza la fuente."""
        state.touched(kb_id)
        return ingest.ingest_text(kb_id, title, text, source_path=source_path, chunk_chars=chunk_chars, root=root)

    @server.tool(annotations=writes)
    @_safe
    def ingest_file(kb_id: str, path: str, title: str | None = None, chunk_chars: int = ingest.DEFAULT_CHUNK_CHARS) -> dict[str, Any]:
        """Como `ingest_text` pero leyendo un archivo del disco del servidor: `.md` y `.txt` siempre,
        `.pdf` si pypdf está instalado. `title` por defecto es el nombre del archivo."""
        state.touched(kb_id)
        return ingest.ingest_file(kb_id, path, title=title, chunk_chars=chunk_chars, root=root)

    @server.tool(annotations=read_only)
    @_safe
    def get_chunk(kb_id: str, chunk_id: str) -> dict[str, Any]:
        """El texto completo de un fragmento ingerido (`<source_id>-chunk-<n>`), con su fuente y offsets."""
        return ingest.get_chunk(kb_id, chunk_id, root)

    @server.tool(annotations=read_only)
    @_safe
    def list_sources(kb_id: str) -> dict[str, Any]:
        """Las fuentes ingeridas en la KB y cuántos fragmentos tiene cada una."""
        return {"sources": ingest.list_sources(kb_id, root)}

    # -- tutores ---------------------------------------------------------------------------

    @server.tool(annotations=read_only)
    @_safe
    def list_tutors(kb_id: str) -> dict[str, Any]:
        """Los roles de tutor declarados en la KB (`AgentDoc`): rol, título, resumen y proyección."""
        return {"tutors": authoring.list_tutors(kb_id, root)}

    @server.tool(annotations=writes)
    @_safe
    def upsert_tutor(kb_id: str, role: str, framing: str, instructions: str, title: str | None = None) -> dict[str, Any]:
        """Declara o actualiza un tutor: `role` (p. ej. tutor, evaluador), `framing` (quién es: persona,
        audiencia, tono), `instructions` (normas al responder: citar átomos, no inventar, idioma…).
        Crea también su proyección (átomos + ramas, solo lectura)."""
        state.touched(kb_id)
        return authoring.upsert_agent(kb_id, role, framing, instructions, title, root=root)

    @server.tool(annotations=calls_model)
    @_safe
    def run_turn(kb_id: str, question: str, role: str = "tutor", model: str | None = None, conversation_id: str | None = None, k: int = 8) -> dict[str, Any]:
        """Un turno del tutor: arma la mesa (los átomos que ve) y responde con el modelo. `model` por
        defecto es TUTOR_MODEL (o "test", que responde sin red citando la mesa); otros: `openai:gpt-4o-mini`,
        `anthropic:claude-sonnet-4-5`, `google-gla:gemini-2.5-flash` (requieren su API key en el servidor).
        Pasa el `conversation_id` devuelto para seguir la misma conversación (memoria en el servidor)."""
        from tutor.agent import Conversation

        kb = state.kb(kb_id)
        chosen_model = model or default_model()
        conversation_id = conversation_id or uuid.uuid4().hex[:12]
        conversation = state.conversations.get(conversation_id)
        if conversation is None or conversation.kb.name != kb.name:
            conversation = Conversation(kb=kb, model=chosen_model, role=role, k=k)
            state.conversations[conversation_id] = conversation
        conversation.kb, conversation.model, conversation.role, conversation.k = kb, chosen_model, role, k
        turn = conversation.ask(question)
        return {"conversation_id": conversation_id, "turn": turn.mesa.get("turn"), "reply": turn.reply, "model": turn.model, "mesa": turn.mesa, "usage": turn.usage}

    @server.tool(annotations=read_only)
    @_safe
    def inspect_context(kb_id: str, question: str, role: str = "tutor", k: int = 8) -> dict[str, Any]:
        """La mesa que vería el tutor para `question` SIN llamar al LLM: átomos elegidos con puntaje y
        razón, y el log de razonamiento del ruteador. Sirve para depurar cobertura de la KB."""
        from tutor.agent import build_context

        return build_context(state.kb(kb_id), question, role=role, k=k)

    @server.tool(annotations=read_only)
    @_safe
    def benchmark_tutor(kb_id: str, questions: list[BenchmarkQuestion], role: str = "tutor", k: int = 5) -> dict[str, Any]:
        """Mide la recuperación del tutor sin LLM: para cada pregunta compara los átomos de la mesa
        (`inspect_context`) y del índice (`search_atoms`) con `expected_atom_ids`. Devuelve hit@1, hit@k y
        MRR por método y el detalle por pregunta."""
        return _benchmark(state.kb(kb_id), questions, role, k)

    # -- recursos y prompts ------------------------------------------------------------

    @server.resource("tutor://{kb_id}/atom/{atom_id}", name="atom", mime_type="text/markdown", description="El markdown de un átomo o rama de la KB.")
    def atom_resource(kb_id: str, atom_id: str) -> str:
        try:
            kb = state.kb(kb_id)
            return kb.render(kb.get(atom_id).key)
        except (AuthoringError, KeyError) as error:
            return f"(no disponible: {_first_line(error)})"

    @server.resource("tutor://{kb_id}/agent/{role}", name="agent", mime_type="text/markdown", description="El AgentDoc del rol: encuadre e instrucciones del tutor.")
    def agent_resource(kb_id: str, role: str) -> str:
        try:
            kb = state.kb(kb_id)
            agent = world.agent(kb, role)
            if agent is None:
                return f"(la KB {kb_id} no declara el rol {role})"
            return kb.render(kb.get(agent["id"]).key)
        except AuthoringError as error:
            return f"(no disponible: {_first_line(error)})"

    @server.prompt(description="Guía para poblar una KB desde una fuente: ingesta, átomos atómicos, tags, procedencia, validación y prueba.")
    def author_kb(kb_id: str) -> str:
        return AUTHOR_PROMPT.format(kb_id=kb_id)

    @server.prompt(description="Encuadre del tutor de una KB para conversar con él por run_turn.")
    def tutor_session(kb_id: str, role: str = "tutor") -> str:
        framing = instructions = ""
        try:
            agent = world.agent(state.kb(kb_id), role) or {}
            framing, instructions = str(agent.get("framing") or ""), str(agent.get("instructions") or "")
        except AuthoringError:
            pass
        return SESSION_PROMPT.format(kb_id=kb_id, role=role, framing=framing or "(sin encuadre: usa upsert_tutor)", instructions=instructions or "(sin instrucciones)")

    server.state = state  # type: ignore[attr-defined]  # para pruebas y selftest
    return server


AUTHOR_PROMPT = """\
Vas a poblar la KB `{kb_id}` con conocimiento atómico a partir de una fuente. Sigue este flujo:

1. Si la KB no existe, `create_kb`. Mira `kb_stats` y `list_branches` para conocer la taxonomía actual.
2. Ingiere la fuente con `ingest_text` (pega el texto) o `ingest_file` (ruta en el servidor). Recibirás
   fragmentos con `chunk_id`; léelos con `get_chunk` si necesitas el texto completo.
3. Por cada fragmento, propone átomos y escríbelos con `upsert_atom`. Un átomo = UNA afirmación
   verificable en la fuente:
   - `title`: la afirmación en una frase corta (sirve de id: `atom-<slug>`).
   - `question`: la pregunta 5W1H que responde: what (qué es), why (por qué), how (cómo), how_not
     (qué no es / error típico), when, where, for_whom.
   - `answer`: la respuesta curada, 2–6 frases, fiel al texto, sin encabezados markdown.
   - `provenance`: el `chunk_id` del fragmento (y página/sección si se sabe).
   - `tags`: `topic:<concepto>` (uno o dos), `layer:theory|pedagogy|example`, `system:{kb_id}`.
     Un namespace nuevo se declara solo; úsalo con criterio y de forma consistente.
   - `parent`: una rama. Crea ramas por tema con `upsert_branch` (padre `branch-{kb_id}`) antes de
     colgar átomos; pocas ramas bien nombradas valen más que muchas.
4. Relaciona átomos que se necesitan o contrastan con `link_atoms` (`requires`, `contrasts_with`,
   `example_of`), con una `description` del tipo la primera vez.
5. `validate_kb` → debe dar `ok: true`. Si no, corrige lo que nombra cada error y vuelve a validar.
6. Prueba: `inspect_context` con 3–5 preguntas típicas para ver si la mesa trae los átomos correctos;
   `run_turn` (model "test" no gasta) para ver la respuesta; `benchmark_tutor` con preguntas y
   `expected_atom_ids` para medir hit@k y MRR. Si falla la cobertura, afina títulos/respuestas o
   agrega átomos, no inventes contenido que la fuente no respalda.
7. Si hace falta, ajusta el encuadre del tutor con `upsert_tutor` (quién es, para quién, normas).
"""

SESSION_PROMPT = """\
Vas a conversar con el tutor `{role}` de la KB `{kb_id}` a través de `run_turn` (pasa siempre el
`conversation_id` que te devuelva para mantener el hilo). El tutor responde solo con lo que hay en
sus átomos y cita sus ids entre corchetes.

Encuadre del tutor:
{framing}

Normas que sigue:
{instructions}

Haz preguntas como lo haría un estudiante; si una respuesta queda corta, mira `inspect_context` para
ver qué átomos tenía a la vista y si falta conocimiento en la KB.
"""


# --------------------------------------------------------------------------------------------
# Lógica de las tools que no vive en otro módulo
# --------------------------------------------------------------------------------------------


def _search(kb: Any, query: str, k: int) -> list[dict[str, Any]]:
    """`world.rank` (índice) más coincidencia léxica en título/tags/respuesta; unión ordenada por puntaje."""
    from tutor.embedding import normalize

    k = max(1, min(int(k), 50))
    scores: dict[str, tuple[float, list[str]]] = {}
    for atom_id, score in world.rank(kb, query, k * 2):
        scores[atom_id] = (round(float(score), 4), [f"semantic:{score:.2f}"])
    tokens = {t for t in re.findall(r"[a-z0-9]+", normalize(query)) if len(t) >= 3 and t not in STOPWORDS}
    for atom in world.list_atoms(kb):
        haystack = normalize(" ".join([atom["title"], " ".join(atom["tags"]), str(atom.get("summary") or "")]))
        title = normalize(atom["title"])
        hits = [t for t in tokens if t in haystack]
        if not hits:
            continue
        bonus = 0.08 * len(hits) + (0.15 if any(t in title for t in hits) else 0.0)
        score, why = scores.get(atom["id"], (0.0, []))
        scores[atom["id"]] = (round(score + bonus, 4), [*why, f"lexical:{','.join(sorted(hits))}"])
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1][0], kv[0]))[:k]
    results = []
    for atom_id, (score, why) in ranked:
        atom = world.get_atom(kb, atom_id) or {}
        summary = str(atom.get("summary") or "")
        results.append({"id": atom_id, "title": atom.get("title"), "score": score, "why": "; ".join(why), "tags": atom.get("tags"), "parent": atom.get("parent"), "question": atom.get("question"), "summary": summary[:280] + ("…" if len(summary) > 280 else "")})
    return results


def _benchmark(kb: Any, questions: list[BenchmarkQuestion], role: str, k: int) -> dict[str, Any]:
    """hit@1, hit@k y MRR para dos métodos: la mesa del tutor (`build_context`) y el índice (`world.rank`).
    Usa `benchmarks.run.evaluate` si el paquete está al alcance; si no, la misma fórmula local."""
    from tutor.agent import build_context

    if not questions:
        raise AuthoringError("no hay preguntas", "pasa [{question, expected_atom_ids}] con al menos una")
    k = max(1, int(k))
    methods = {
        "mesa": lambda q, kk: list(build_context(kb, q, role=role, k=kk)["atom_ids"]),
        "embed": lambda q, kk: [atom_id for atom_id, _ in world.rank(kb, q, kk)],
    }
    known = {d.name for d in kb.by_model(world.KNOWLEDGE_MODEL)}
    unknown = sorted({a for q in questions for a in q.expected_atom_ids if a not in known})
    results: dict[str, Any] = {"k": k, "n_questions": len(questions), "role": role, "unknown_expected_ids": unknown, "methods": {}}
    for name, method in methods.items():
        rows, metrics = _evaluate(method, questions, k)
        results["methods"][name] = {"metrics": metrics, "per_question": rows}
    return results


def _evaluate(method: Callable[[str, int], list[str]], questions: list[BenchmarkQuestion], k: int) -> tuple[list[dict[str, Any]], dict[str, float]]:
    try:
        from benchmarks.run import Question, evaluate

        bench_questions = [Question(q.id or f"q{i + 1}", q.question, tuple(q.expected_atom_ids), ()) for i, q in enumerate(questions)]
        rows, metrics = evaluate(method, bench_questions, k, {})
        return rows, {key: value for key, value in metrics.items() if not key.startswith("tag_hit")}
    except ImportError:
        pass
    rows: list[dict[str, Any]] = []
    for i, q in enumerate(questions):
        ids = list(method(q.question, k))[:k]
        expected = set(q.expected_atom_ids)
        rank = next((j + 1 for j, atom_id in enumerate(ids) if atom_id in expected), None)
        rows.append({"id": q.id or f"q{i + 1}", "top": ids, "first_hit_rank": rank, "hit@1": int(rank == 1), "hit@k": int(rank is not None), "rr": 1 / rank if rank else 0.0})
    n = max(len(rows), 1)
    return rows, {"hit@1": sum(r["hit@1"] for r in rows) / n, f"hit@{k}": sum(r["hit@k"] for r in rows) / n, "mrr": sum(r["rr"] for r in rows) / n}


# --------------------------------------------------------------------------------------------
# Transportes
# --------------------------------------------------------------------------------------------


class BearerTokenMiddleware:
    """ASGI: exige `Authorization: Bearer <token>` en toda petición HTTP (comparación en tiempo constante)."""

    def __init__(self, app: Any, token: str) -> None:
        self.app, self.token = app, token

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        header = next((v for k, v in scope.get("headers") or [] if k == b"authorization"), b"").decode("latin-1")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(token.strip(), self.token):
            body = json.dumps({"error": "unauthorized", "hint": "Authorization: Bearer <TUTOR_MCP_TOKEN>"}).encode()
            await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer"), (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def http_app(server: MCPServer, host: str, token: str | None) -> Any:
    """La app Starlette del transporte streamable HTTP (en `/mcp`), con el Bearer si hay token."""
    app = server.streamable_http_app(streamable_http_path=HTTP_PATH, host=host)
    if token:
        return BearerTokenMiddleware(app, token)
    log.warning("%s no está definido: el servidor HTTP acepta cualquier cliente", ENV_TOKEN)
    return app


def serve_http(server: MCPServer, address: str) -> None:
    import uvicorn

    host, _, port = address.rpartition(":")
    host = host or "127.0.0.1"
    app = http_app(server, host, os.environ.get(ENV_TOKEN) or None)
    log.info("tutor-mcp escuchando en http://%s:%s%s", host, port, HTTP_PATH)
    uvicorn.run(app, host=host, port=int(port or 8200), log_level="info")


# --------------------------------------------------------------------------------------------
# Autoprueba
# --------------------------------------------------------------------------------------------

SELFTEST_TEXT = (
    "Una acción es una transformación de objetos matemáticos que el sujeto percibe como externa y que "
    "ejecuta paso a paso siguiendo indicaciones explícitas.\n\n"
    "Cuando la acción se repite y el sujeto reflexiona sobre ella, se interioriza en un proceso: una "
    "construcción mental que puede ejecutarse sin estímulos externos, imaginarse y revertirse.\n\n"
    "Un proceso se encapsula en un objeto cuando el sujeto lo concibe como una totalidad sobre la que "
    "pueden aplicarse nuevas acciones."
)


def selftest(root: Path | None = None, out: Any = None) -> int:
    """Crea una KB `demo` en un tmpdir y recorre las tools a través de un cliente MCP en proceso."""
    out = out or sys.stdout
    tmp = tempfile.TemporaryDirectory(prefix="tutor-mcp-selftest-") if root is None else None
    base = Path(tmp.name) if tmp else root
    try:
        return asyncio.run(_selftest(base, out))
    finally:
        if tmp:
            tmp.cleanup()


async def _selftest(base: Path, out: Any) -> int:
    from mcp.client.client import Client

    server = build(base)
    failures = 0

    def step(name: str, result: Any, ok: bool = True) -> Any:
        nonlocal failures
        mark = "ok " if ok else "FAIL"
        summary = json.dumps(result, ensure_ascii=False, default=str)
        print(f"[{mark}] {name}: {summary[:240]}{'…' if len(summary) > 240 else ''}", file=out)
        failures += 0 if ok else 1
        return result

    async with Client(server) as client:
        tools = [t.name for t in (await client.list_tools()).tools]
        step("list_tools", tools, {"create_kb", "upsert_atom", "run_turn", "benchmark_tutor"} <= set(tools))

        async def call(name: str, **args: Any) -> dict[str, Any]:
            return tool_result(await client.call_tool(name, args))

        kb = await call("create_kb", kb_id="demo", title="Demo APOS", description="KB de autoprueba")
        step("create_kb", kb, kb.get("valid") is True)
        branch = await call("upsert_branch", kb_id="demo", title="Estructuras mentales", parent="branch-demo", summary="Acción, proceso, objeto")
        step("upsert_branch", branch, branch.get("id") == "branch-estructuras-mentales")
        ingested = await call("ingest_text", kb_id="demo", title="Fuente demo", text=SELFTEST_TEXT, chunk_chars=300)
        step("ingest_text", {"source_id": ingested.get("source_id"), "n_chunks": ingested.get("n_chunks")}, ingested.get("n_chunks", 0) >= 2)
        chunk_ids = [c["chunk_id"] for c in ingested.get("chunks", [])]
        atoms = [
            ("La acción es una transformación externa paso a paso", "what", "Una acción es una transformación de objetos que el sujeto percibe como externa y ejecuta paso a paso con indicaciones explícitas.", ["topic:accion", "layer:theory"]),
            ("El proceso es la interiorización de la acción", "how", "Al repetir la acción y reflexionar sobre ella, se interioriza en un proceso: una construcción mental ejecutable sin estímulos externos.", ["topic:proceso", "layer:theory"]),
            ("El objeto es la encapsulación de un proceso", "what", "Un proceso se encapsula en un objeto cuando se concibe como una totalidad sobre la que pueden aplicarse nuevas acciones.", ["topic:objeto", "layer:theory"]),
        ]
        ids: list[str] = []
        for i, (title, question, answer, tags) in enumerate(atoms):
            atom = await call("upsert_atom", kb_id="demo", title=title, question=question, answer=answer, provenance=chunk_ids[min(i, len(chunk_ids) - 1)], tags=[*tags, "system:demo"], parent=branch["id"])
            step(f"upsert_atom[{i}]", {"id": atom.get("id"), "created": atom.get("created")}, bool(atom.get("id")))
            ids.append(atom.get("id", ""))
        link = await call("link_atoms", kb_id="demo", source=ids[1], relation="requires", target=ids[0], description="El origen presupone el destino.")
        step("link_atoms", link, "relation" in link)
        valid = await call("validate_kb", kb_id="demo")
        step("validate_kb", {"ok": valid.get("ok"), "errors": valid.get("errors"), "by_model": (valid.get("stats") or {}).get("by_model")}, valid.get("ok") is True)
        found = await call("search_atoms", kb_id="demo", query="qué es la encapsulación de un proceso en un objeto", k=3)
        top = [r["id"] for r in found.get("results", [])]
        step("search_atoms", top, bool(top) and top[0] == ids[2])
        chunk = await call("get_chunk", kb_id="demo", chunk_id=chunk_ids[0])
        step("get_chunk", {"chunk_id": chunk.get("chunk_id"), "chars": len(chunk.get("text") or "")}, bool(chunk.get("text")))
        turn = await call("run_turn", kb_id="demo", question="¿Qué es un proceso?", model="test")
        step("run_turn", {"conversation_id": turn.get("conversation_id"), "reply": turn.get("reply"), "atom_ids": (turn.get("mesa") or {}).get("atom_ids")}, bool(turn.get("reply")))
        second = await call("run_turn", kb_id="demo", question="¿Y cómo se vuelve objeto?", model="test", conversation_id=turn.get("conversation_id"))
        step("run_turn[2]", {"turn": second.get("turn"), "retained": (second.get("mesa") or {}).get("retained_atom_ids")}, second.get("turn") == 2)
        mesa = await call("inspect_context", kb_id="demo", question="¿Qué es una acción?")
        step("inspect_context", {"atom_ids": mesa.get("atom_ids"), "summary": mesa.get("reasoning_summary")}, bool(mesa.get("atom_ids")))
        bench = await call("benchmark_tutor", kb_id="demo", questions=[{"question": "¿Qué es una acción?", "expected_atom_ids": [ids[0]]}, {"question": "¿Cómo se encapsula un proceso?", "expected_atom_ids": [ids[2]]}], k=3)
        step("benchmark_tutor", {m: v["metrics"] for m, v in (bench.get("methods") or {}).items()}, "methods" in bench)
        resource = await client.read_resource(f"tutor://demo/atom/{ids[0]}")
        text = getattr(resource.contents[0], "text", "")
        step("resource atom", text.splitlines()[0:2], text.startswith("---"))
        prompt = await client.get_prompt("author_kb", {"kb_id": "demo"})
        prompt_text = getattr(prompt.messages[0].content, "text", "")
        step("prompt author_kb", prompt_text[:80], "ingest_text" in prompt_text)
        deleted = await call("delete_atom", kb_id="demo", atom_id=ids[1])
        step("delete_atom", deleted, deleted.get("deleted") == ids[1])
        valid = await call("validate_kb", kb_id="demo")
        step("validate_kb[2]", {"ok": valid.get("ok"), "errors": valid.get("errors")}, valid.get("ok") is True)
        bad = await call("get_atom", kb_id="demo", atom_id="atom-no-existe")
        step("error shape", bad, set(bad) == {"error", "hint"})
    print(f"\nselftest: {'OK' if failures == 0 else f'{failures} fallos'} ({base})", file=out)
    return 0 if failures == 0 else 1


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    parser = argparse.ArgumentParser(prog="tutor-mcp", description=__doc__.split("\n\n")[0])
    parser.add_argument("--http", metavar="HOST:PORT", help="Servir por streamable HTTP en vez de stdio (p. ej. 0.0.0.0:8200).")
    parser.add_argument("--kbs-root", type=Path, default=None, help=f"Raíz de las KBs (default {authoring.ENV_ROOT} o kbs/).")
    parser.add_argument("--selftest", action="store_true", help="Autoprueba completa en un tmpdir; exit 0 si todo pasa.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    if args.selftest:
        return selftest(args.kbs_root)
    server = build(args.kbs_root)
    if args.http:
        serve_http(server, args.http)
        return 0
    server.run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
