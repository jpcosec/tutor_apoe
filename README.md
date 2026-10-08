# Tutor APOE

Repositorio de trabajo para extraer, organizar y consultar conocimiento sobre APOS/ APOE usando **Deskops** y **SLDB**.

Desde octubre de 2026 el repo es además la base de dos piezas reutilizables:

1. **Infra de agentes con KB** (`runtime/` + `src/tutor/`): un tutor es un agente
   pydantic-ai cuyo contexto se arma por turno desde una KB sldb (`ContextRouter`
   + embeddings + jerarquía; opcionalmente Jev/TypeSafe como selector). La KB de
   APOS vive en `kbs/apos/` y se regenera desde `desk/atoms/`.
2. **Servidor MCP** (`tutor-mcp`): crear, poblar (por chat o por ingesta de
   texto/PDF), validar y probar KBs y tutores desde Claude Desktop o cualquier
   cliente MCP. Ver [`docs/mcp.md`](docs/mcp.md).

## Arranque rápido

```bash
./scripts/bootstrap_deps.sh         # sldb y pron vía google `repo` → third_party/
pip install -r requirements.txt     # paquetes vendoreados (runtime/) + tutor, editable
export TUTOR_EMBEDDER=hash          # sin red; `fastembed` requiere el extra `embed`

tutor kb build                      # desk/atoms → kbs/apos (idempotente, ~30 s)
tutor kb validate --kb kbs/apos
tutor kb rank --kb kbs/apos "qué es la encapsulación" --k 5
tutor ask --kb kbs/apos --model test "¿Qué diferencia una acción de un proceso?"
tutor web --kb kbs/apos --model test --port 8300     # UI de chat con la mesa por turno
tutor-mcp --selftest                                 # MCP: crea una KB demo y la ejercita
```

`--model test` no usa red. Con una API key exportada: `--model google:gemini-2.5-flash`,
`openai:gpt-4o-mini`, `openrouter:...`. Variables en `.env.example`.

**Secrets y config:** no hay `.env` en el repo. `direnv allow` una vez y `.envrc` carga los
secrets desde `~/setup/.env-collection/master.env` (fuera de git) y la config versionada de
`.env.defaults` (DeepSeek V4.1 Flash vía OpenRouter como LLM, Jev/TypeSafe como selector de
contexto, embedder hash).
Con eso `tutor ask "..."` y `tutor web` corren con el stack real sin flags.

**Entrega aislada (Docker):**

```bash
docker build -f docker/Dockerfile -t tutor-apoe .
docker run --rm tutor-apoe                  # scripts/docker_smoke.sh: instala, construye KB, MCP, tests
docker compose up -d                        # MCP por HTTP en :8200, KBs en un volumen (docs/mcp.md)
```

Benchmark de retrieval (20 preguntas, `benchmarks/`): `python -m benchmarks.run --k 5`.
Mapa del código: `runtime/<paquete>/README.md`, `kbs/README.md`, `docs/mcp.md`.

## Consulta simple de la KB

No necesitas usar un chatbot ni configurar claves de IA. Desde la Terminal:

```bash
cd /Users/investigacion/proyectos/tutor_apoe
python scripts/kb.py serve
```

Luego abre <http://127.0.0.1:8000>. El visor muestra un mapa interactivo de la
KB con React Flow: árbol horizontal o vertical, zoom, minimapa, filtros por
tema y un panel con la respuesta y procedencia de cada átomo. Para detenerlo,
vuelve a la Terminal y presiona `Control + C`.

Selecciona una tarjeta de átomo para abrir el editor a la derecha. Al guardar,
se actualiza el archivo Markdown y se reindexa SLDB automáticamente.

Los átomos pueden declarar `node_type` (texto libre, por ejemplo `branch`,
`example` o `definition`) y `parent_id`. Usa **Add child** en el editor para
crear un átomo hijo enlazado a la tarjeta actual.

También hay una interfaz de comandos respaldada por **SLDB**:

```bash
python scripts/kb.py search topic:encapsulation
python scripts/kb.py check
```

`search` delega la consulta a `sldb find`; por eso puede buscar texto y tags
semánticos como `topic:schema` o `layer:pedagogy`.

## Estructura

- `sources/` — fuentes primarias, por ejemplo el PDF base.
- `desk/` — superficies operativas de Deskops.
  - `desk/tasks/` — board y tasks activas.
  - `desk/contexts/` — pills/contexto reusable.
  - `desk/rituals/` — ejecución, testing y cierre.
- `knowledge/` — base de conocimiento estructurada sobre SLDB.
  - `knowledge/source-notes/` — notas pegadas a fragmentos fuente con localización precisa.
  - `knowledge/atoms/` — átomos de conocimiento destilados.
- `knowledge_models/` — modelos locales SLDB para notas fuente y átomos.
- `.sldb/` — store/index de SLDB.
- `docs/` — diagramas y documentación de arquitectura.

## Qué hay aquí hoy

- Un desk inicializado con Deskops.
- Un árbol taxonómico para átomos APOS.
- Un conjunto inicial de átomos en `desk/atoms/` heredado de la fase operativa.
- Una nueva capa de conocimiento en `knowledge/` respaldada por modelos locales de SLDB.
- Un store `.sldb` listo para búsqueda e indexación.

## Requisitos

Necesitas tener instalados:

- `deskops`
- `sldb`

Comprobación rápida:

```bash
deskops --help
sldb --help
```

## Uso básico con Deskops

### Ver el board

```bash
deskops show board Board --root .
```

### Listar tasks

```bash
deskops list tasks --root .
```

### Crear una task

```bash
deskops add task --root . \
  --title "Extraer átomos del capítulo 8" \
  --why "Necesitamos completar la cobertura temática" \
  --goal "Agregar átomos nuevos sobre niveles y totality" \
  --scope "desk/atoms/apos/mechanisms y dominios relacionados"
```

### Ver una task

```bash
deskops show task <task-id> --root .
```

### Avanzar una task

```bash
deskops advance task <task-id> --root .
```

### Ver siguiente acción sugerida

```bash
deskops next <task-id> --root .
```

## Arquitectura recomendada

- Usa **Deskops** para gestionar el trabajo operativo.
- Usa **SLDB + modelos locales** para construir la base de conocimiento.

Documento de referencia:

- `docs/knowledge-architecture.md`

## Uso básico con átomos en Deskops

### Listar átomos

```bash
deskops list atoms --root .
```

### Ver un átomo

```bash
deskops show atom <atom-id> --root .
```

### Crear un átomo manualmente

```bash
deskops add atom --root . \
  --title "APOS distingue Acción y Proceso" \
  --five-wh-one-plus what \
  --answer "En APOS, la Acción requiere guía externa explícita, mientras que el Proceso permite control mental interno de la transformación."
```

## Uso básico con SLDB

SLDB sirve para **trackear, indexar, buscar y validar** los documentos estructurados del repo.

En este repo, el uso recomendado es:

- `SourceNoteDoc` para notas ancladas a párrafos fuente
- `KnowledgeAtomDoc` para átomos con `provenance` estructurado en frontmatter

### Verificar el store

```bash
sldb stores check --store .sldb
```

### Reindexar el store

Haz esto después de mover, crear o editar átomos/documentos:

```bash
sldb stores update --store .sldb --pythonpath .
```

### Listar documentos trackeados

```bash
sldb docs list --store .sldb
```

### Buscar por texto o ruta física

```bash
sldb find apos --in physical --store .sldb --pythonpath .
sldb find desk/atoms --in physical --store .sldb --pythonpath .
```

### Buscar semánticamente por tags

```bash
sldb find system:apos --in semantic --store .sldb --pythonpath .
sldb find topic:totality --in semantic --store .sldb --pythonpath .
sldb find topic:schema --in semantic --store .sldb --pythonpath .
```

### Inspeccionar un documento trackeado

```bash
sldb docs show atom-apos-is-a-constructivist-theory-of-learning-mathematics --store .sldb
```

### Ver modelos locales

```bash
sldb models show SourceNoteDoc --store .sldb --pythonpath .
sldb models show KnowledgeAtomDoc --store .sldb --pythonpath .
```

### Crear una nota fuente

```bash
sldb docs create --model SourceNoteDoc \
  -o knowledge/source-notes/apos/note-ejemplo.md \
  '{"id":"note-ejemplo","title":"Nota ejemplo","source_path":"sources/archivo.pdf","source_title":"Archivo","chapter":"1","section":"1.1","page_start":1,"page_end":1,"anchor_text":"Texto ancla","excerpt":"Cita breve","note":"Observación estructurada","tags":["system:apos","topic:example","layer:source","domain:mathematics-education"]}' \
  --store .sldb --pythonpath .
```

### Crear un átomo con provenance en frontmatter

```bash
sldb docs create --model KnowledgeAtomDoc \
  -o knowledge/atoms/apos/atom-ejemplo.md \
  '{"id":"atom-ejemplo","title":"Átomo ejemplo","question":"what","answer":"Respuesta breve.","provenance":[{"source_path":"sources/archivo.pdf","source_title":"Archivo","chapter":"1","section":"1.1","page_start":1,"page_end":1,"anchor_text":"Texto ancla","excerpt":"Cita breve"}],"tags":["system:apos","topic:example","layer:theory","domain:mathematics-education"]}' \
  --store .sldb --pythonpath .
```

## Flujo recomendado para trabajar con este repo

### 1. Recuperar estado

```bash
deskops show board Board --root .
deskops list tasks --root .
sldb stores check --store .sldb
```

### 2. Leer la fuente

Las fuentes primarias viven en `sources/`.

### 3. Extraer conocimiento

- crear o refinar átomos en `desk/atoms/`
- agregar `tags`
- agregar `Procedencia`
- mantener cada átomo pequeño y atómico

### 4. Reindexar

```bash
sldb stores update --store .sldb --pythonpath .
```

### 5. Consultar y deduplicar

```bash
deskops list atoms --root .
sldb find topic:genetic-decomposition --in semantic --store .sldb --pythonpath .
sldb find topic:repeating-decimals --in semantic --store .sldb --pythonpath .
```

## Convención de átomos usada aquí

Cada átomo idealmente incluye:

- una sola idea durable
- `tags` namespaced, por ejemplo:
  - `system:apos`
  - `topic:schema`
  - `layer:theory`
  - `domain:mathematics-education`
- `## Respuesta`
- `## Procedencia`

## Ejemplos útiles

### Ver el árbol de átomos

```bash
find desk/atoms -type f | sort
```

### Contar átomos

```bash
find desk/atoms -type f -name 'atom-*.md' | wc -l
```

### Buscar átomos sobre un tema

```bash
sldb find topic:infinity --in semantic --store .sldb --pythonpath .
```

## Nota

Deskops gestiona el **workflow** del repo.
SLDB gestiona la **superficie documental estructurada** y su indexación.

Piensa así:

- **Deskops** = tareas, board, rituales, operación
- **SLDB** = documentos, tracking, búsqueda, store
