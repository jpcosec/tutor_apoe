# tutor-mcp — servidor MCP del tutor

Un servidor MCP (SDK oficial `mcp` 2.x) para hacer dos cosas desde cualquier cliente MCP
(Claude Desktop, Claude Code, Cursor…):

1. **Crear, poblar y mantener KBs** sldb del tutor: desde el chat (`upsert_atom`) o desde una
   fuente (`ingest_text`/`ingest_file` → fragmentos → el LLM cliente propone átomos). El servidor
   no llama a ningún LLM para la autoría: valida con el esquema `kb_models`, escribe con sldb y
   valida con `kb` (V0–V13).
2. **Levantar y probar tutores** sobre esas KBs: `run_turn` (respuesta + mesa), `inspect_context`
   (la mesa sin LLM), `benchmark_tutor` (hit@k / MRR).

Código: `src/tutor/mcp_server.py` (tools, recursos, prompts, transportes), `src/tutor/authoring.py`
(escritura), `src/tutor/ingest.py` (fuentes). Esquema nuevo: `kbs/kb_models/ingest.py`
(`SourceDoc`, `SourceChunk`).

## Arrancar

```bash
tutor-mcp                                  # stdio (default)
tutor-mcp --kbs-root /datos/kbs            # dónde viven las KBs
tutor-mcp --http 0.0.0.0:8200              # streamable HTTP en http://host:8200/mcp
tutor-mcp --selftest                       # autoprueba sin red: KB temporal, todas las tools, exit 0
python -m tutor.mcp_server --selftest      # sin instalar el paquete (con el PYTHONPATH del repo)
```

Con `--http`, si `TUTOR_MCP_TOKEN` está definido toda petición debe llevar
`Authorization: Bearer <token>` (si no, 401). Sin la variable el servidor acepta a cualquiera y lo
avisa en el log: úsalo solo en local.

## Conectarlo

**Claude Desktop (stdio)** — `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tutor": {
      "command": "tutor-mcp",
      "env": {
        "TUTOR_KBS_ROOT": "/ruta/a/kbs",
        "TUTOR_MODEL": "test"
      }
    }
  }
}
```

Si el paquete no está instalado, usa `"command": "python", "args": ["-m", "tutor.mcp_server"]` con
`PYTHONPATH` apuntando a `src`, `kbs` y `runtime/*/src` (ver `tests/tutor/conftest.py`).

**Conector remoto por URL (streamable HTTP + token)**: levanta
`TUTOR_MCP_TOKEN=... tutor-mcp --http 0.0.0.0:8200` detrás de HTTPS y registra en el cliente la URL
`https://tu-host/mcp` con la cabecera `Authorization: Bearer <token>` (en Claude: *Settings →
Connectors → Add custom connector*; en Claude Code: `claude mcp add --transport http tutor
https://tu-host/mcp --header "Authorization: Bearer <token>"`).

## Tools

| Grupo | Tool | Qué hace |
|---|---|---|
| KBs | `list_kbs` | KBs bajo la raíz: id, átomos, ramas, roles, si valida |
| | `create_kb(kb_id, title, language, description)` | KB vacía pero válida: rama raíz `branch-<kb_id>`, categorías, `child_of`, tutor por defecto |
| | `validate_kb(kb_id)` | `{ok, errors, warnings, stats}` con la validación real de `kb` |
| | `rebuild_kb(kb_id)` | rehace `.sldb/` e índice desde los `.md` (tras mover la KB o editar a mano) |
| | `kb_stats(kb_id)` | conteos, ramas de primer nivel, fuentes, embedder |
| Átomos | `search_atoms(kb_id, query, k)` | índice de embeddings + coincidencia léxica (título, tags, respuesta) |
| | `get_atom(kb_id, atom_id)` | átomo o rama completo, hijos, relaciones y markdown |
| | `list_branches(kb_id)`, `children(kb_id, atom_id)` | la taxonomía |
| | `upsert_atom(kb_id, title, answer, provenance, parent, question, tags, id)` | crea/actualiza un `KnowledgeAtom` (+ `child_of`, namespaces nuevos, índice) |
| | `upsert_branch(kb_id, title, parent, summary, id)` | crea/actualiza un `BranchNode` |
| | `delete_atom(kb_id, atom_id)` | borra átomo (o rama sin hijos) y sus relaciones |
| | `link_atoms(kb_id, source, relation, target, description)` | relación tipada; declara el tipo si falta |
| Ingesta | `ingest_text(kb_id, title, text, chunk_chars)` | guarda `SourceDoc` + `SourceChunk`s y devuelve los fragmentos |
| | `ingest_file(kb_id, path, title, chunk_chars)` | idem desde `.md`/`.txt` (y `.pdf` con pypdf) |
| | `get_chunk(kb_id, chunk_id)`, `list_sources(kb_id)` | leer fragmentos y fuentes |
| Tutores | `list_tutors(kb_id)` | roles con `AgentDoc` |
| | `upsert_tutor(kb_id, role, framing, instructions, title)` | `AgentDoc` + `ProjectionDoc` del rol |
| | `run_turn(kb_id, question, role, model, conversation_id, k)` | respuesta + mesa; conversaciones en memoria por id |
| | `inspect_context(kb_id, question, role, k)` | la mesa sin llamar al LLM |
| | `benchmark_tutor(kb_id, questions[{question, expected_atom_ids}], role, k)` | hit@1 / hit@k / MRR para `mesa` y `embed` |

Recursos: `tutor://{kb_id}/atom/{atom_id}` (markdown del átomo o rama) y
`tutor://{kb_id}/agent/{role}` (markdown del `AgentDoc`). Prompts: `author_kb(kb_id)` (guía de
autoría) y `tutor_session(kb_id, role)` (encuadre del tutor para conversar).

Ningún error llega como traceback: las tools devuelven `{"error": "...", "hint": "..."}`.

## Flujo de autoría recomendado

1. `create_kb` → `kb_stats` / `list_branches`.
2. `ingest_text` o `ingest_file`: fragmentos con `chunk_id` (no entran al índice ni los ve el tutor).
3. Por fragmento, `upsert_atom` con **una afirmación por átomo**: `title` corto, `question` 5W1H
   (`what, why, how, how_not, when, where, for_whom`), `answer` fiel a la fuente, `provenance` =
   `chunk_id`, `tags` `namespace:valor` (`topic:`, `layer:`, `system:<kb_id>`), `parent` = una rama
   (`upsert_branch` antes, colgando de `branch-<kb_id>`).
4. `link_atoms` para `requires`, `contrasts_with`, `example_of`…
5. `validate_kb` → `ok: true`.
6. `inspect_context` / `run_turn` (model `test` no gasta) / `benchmark_tutor`; afinar con
   `upsert_tutor` si hace falta.

El prompt `author_kb` contiene esta guía para el cliente.

## Dónde queda cada cosa en la KB

`knowledge/<id>.md` (átomos), `taxonomy/<id>.md` (ramas), `relations/<tipo>--<src>--<dst>.md`,
`kgdb/relation_types/<tipo>.md`, `categories/category-<ns>.md`, `agent/agent-<rol>-<kb>.md`,
`projections/projection-<rol>.md`, `ingest/sources/<source_id>.md`,
`ingest/chunks/<source_id>/<chunk_id>.md`. `.sldb/` es derivado (rutas absolutas de la máquina):
`rebuild_kb` lo regenera.

## Variables de entorno

| Variable | Para qué | Default |
|---|---|---|
| `TUTOR_KBS_ROOT` | raíz de las KBs (`<root>/<kb_id>/kb.yaml`); `--kbs-root` la pisa | `kbs/` del repo |
| `TUTOR_MODEL` | modelo por defecto de `run_turn` (`test`, `openai:gpt-4o-mini`, `anthropic:claude-sonnet-4-5`, `google-gla:gemini-2.5-flash`…) | `test` |
| `TUTOR_EMBEDDER` | embedder de las KBs nuevas y con el que se abren (`hash`, `fastembed[:modelo]`) | `hash` (el que declara `kb.yaml`) |
| `TUTOR_MCP_TOKEN` | Bearer obligatorio en `--http`; sin definir, acepta a todos (warning) | — |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`, `OPENROUTER_API_KEY`, credenciales AWS (bedrock) | las que necesite el `model` elegido en `run_turn` | — |
| `TYPESAFE_API_KEY` | opcional: habilita el selector Jev en `tutor.agent` | — |
