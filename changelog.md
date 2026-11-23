# Changelog de Tutor APOE

Qué hay listo y cómo verlo. Lo más nuevo va primero. Para abrirlo: `./install.sh` y después
`.venv/bin/tutor web --kb kbs/apos --model test --port 8300` (guía en [`install.md`](install.md)).

## 2026-11-23 · Una sola interfaz, wiki de configuración y servidor MCP estándar

### Para mostrar (abrir <http://127.0.0.1:8300>)

Todo está en **un solo menú**: Conversación · Paquetes · Grafo APOS · Scratch · **Experto** ·
**Ejemplos** · **Bibliografía** · **Configuración**.

- **Configuración (nuevo)**: una wiki donde se ve y se edita cómo es el tutor: su encuadre, sus
  instrucciones y sus políticas, como una página con campos. Se guarda al salir de cada campo y
  **vale desde la pregunta siguiente**, sin reiniciar. Los átomos, ramas y relaciones se ven ahí,
  pero no se cambian (su fuente son los átomos de `desk/atoms/`). Un guardado que dejaría la base
  inválida se deshace solo y explica por qué. Enlace directo: `/#config`.
- **Experto, Ejemplos y Bibliografía** ahora son pestañas del mismo menú (antes había que abrir otro
  visor). Son los módulos de entrevista a especialistas LAETEC, de casos y descomposición genética,
  y del catálogo del libro y las investigaciones APOE. Enlaces: `/#expert`, `/#examples`,
  `/#literature`. Las invitaciones a especialistas (`/expert/<código>`) siguen abriendo como página
  sola.
- **Servidor MCP sobre FastMCP**: `tutor-mcp` cambió de SDK para estandarizar con otros proyectos.
  Mismas 31 herramientas, mismos parámetros, misma ruta HTTP `/mcp` y misma clave
  (`TUTOR_MCP_TOKEN`). Se conecta desde Claude Desktop, Claude Code o Codex (guía en
  [`docs/mcp.md`](docs/mcp.md)).

### Para quien instala o desarrolla

- **`./install.sh`**: un comando deja el tutor instalado en `.venv/`, construye la base y la valida
  (5–10 minutos, sin claves). Antes la instalación desde cero estaba rota.
- **La prueba aislada en Docker pasa** (`docker build` + `docker run` terminan en `SMOKE OK`).
- **`tutor kb build` ya no mueve fechas**: reconstruir la base sin cambiar átomos no deja archivos
  modificados en git (antes tocaba 327 archivos).
- **`.sldb/runtime/` dejó de versionarse**: son archivos derivados que sldb regenera.
- **[`AGENTS.md`](AGENTS.md) tiene una guía para agentes que cambian código**: cómo preparar un
  worktree, qué probar, cómo entregar por pull request a `dev` y recetas (agregar una tool al MCP,
  agregar una pestaña al menú, hacer editable otro tipo de página en la wiki, traer código de otro
  proyecto).

### Cosas a tener en cuenta

- Sin clave, el tutor responde con el modelo de prueba (`--model test`): sirve para mostrar la
  interfaz, pero no redacta respuestas reales. Para respuestas reales hace falta `DEEPSEEK_API_KEY`
  en el entorno (ver `install.md`, paso 4).
- Cada guardado en Configuración tarda unos 3 segundos: revalida la base entera.
- Después de actualizar un checkout que ya tenía la base construida, correr una vez
  `tutor kb build`.
- Fuera de esta máquina, la wiki y los módulos piden una clave (`TUTOR_WIKI_KEY`); sin ella solo se
  abren desde `127.0.0.1`.
- Hay tests viejos del visor legacy (`scripts/kb.py`, búsqueda con `sldb find`) que fallan por una
  incompatibilidad conocida de ids de ramas; no afecta a `tutor web`.

## 2026-11-17 a 2026-11-22 · Módulos de investigación (ya estaban en `main`)

Resumen de lo que entró antes, según su historial:

- **Módulo experto APOE** con el protocolo de entrevista LAETEC: invitaciones por especialista,
  pausa y reanudación, exportación de entrevistas para revisión.
- **Módulo de ejemplos APOE y descomposición genética**, con seguimiento de casos.
- **Módulo de libro e investigaciones APOE** (catálogo bibliográfico).
- **Validación experta en cuatro capas**: documento de diseño, doce preguntas de validación e
  instrumentos Word (protocolo, perfil del panel y ficha individual de juicio experto) en
  `docs/validacion-experta/`.
- **Visualizaciones GeoGebra y ManimGL**: puente GeoGebra→Manim, escena de matriz y vector 2×2,
  visualizador de tres rectas con versión autónoma y código de incrustación para LAETEC
  (`visualizations/`).
- **Sugerencias didácticas** (`knowledge/didactic-suggestions/`), consulta guiada en el visor y
  relaciones entre construcciones APOS en las consultas.
