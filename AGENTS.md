# Trabajo en Tutor APOE

Este repositorio es una base de conocimiento sobre la teoría APOS. Mantén el
trabajo pequeño, trazable a una fuente y separado de cualquier runtime de
chatbot.

## Regla de entrega

Cada cambio terminado debe quedar publicado en el remoto. Nunca incluyas archivos
generados de `.sldb/runtime/`, credenciales ni cambios ajenos en un commit: haz
`git add` únicamente de los archivos del cambio, nunca `git add -A`.

- **Contenido de la base** (átomos, fuentes, notas), trabajando sin programar: valida,
  commit claro y `git push origin <rama-actual>`. Lo hace la skill `tutor-guardar-cambios`.
- **Código** (`src/`, `runtime/`, `superficie/`, `docker/`, `scripts/`, tests): va por
  pull request a `dev`, como se explica abajo. `main` solo avanza cuando JP lo pide.

No dejes cambios terminados solamente en la máquina, salvo que la persona usuaria pida
expresamente no hacer commit o push.

## Guía para agentes que cambian código

### 1. Preparar un lugar de trabajo

Un worktree por trabajo pedido, salido de `dev`. El checkout principal puede tener
cambios sin commitear de otra sesión: no lo toques.

```bash
git fetch origin
git worktree add -b <rama> ../tutor_apoe.wt/<rama> origin/dev
cd ../tutor_apoe.wt/<rama>
./install.sh                               # .venv/, sldb y pron, base construida y validada (5–10 min)
export TUTOR_EMBEDDER=hash                 # sin red ni claves
```

Debe terminar con `Instalación lista.`. Detalle y errores comunes en [`install.md`](install.md).
`third_party/sldb`, `third_party/pron`, `.venv/` y `kbs/*/.sldb/` están ignorados por git.

### 2. Probar

| Qué cambiaste | Qué correr |
|---|---|
| Cualquier cosa en `src/tutor/` o `kbs/` | `.venv/bin/python -m pytest tests/tutor -q -p no:cacheprovider` (~5 min) |
| Algo en `runtime/` | `.venv/bin/python -m pytest runtime -q -p no:cacheprovider` |
| El servidor MCP | además `.venv/bin/tutor-mcp --selftest` (debe terminar en `selftest: OK`) |
| `superficie/` | `cd superficie && npm ci && npm test && npm run build` |
| Instalación, dependencias, `docker/` o antes de cerrar un trabajo grande | la prueba aislada, abajo |

`tutor kb build` y los tests no deben dejar archivos modificados en `kbs/apos/` si no
cambiaste átomos: el build conserva la firma de cada página que queda igual. Si
`git status` muestra cambios ahí que no esperabas, míralos antes de commitear.

Prueba aislada (instala desde cero, construye la base, MCP, wiki y todos los tests; ~15 min).
Debe terminar en `SMOKE OK`:

```bash
docker build -f docker/Dockerfile -t tutor-apoe .
docker run --rm tutor-apoe
```

Si el build no alcanza la red (`Connection timed out` en `apt-get`), agrega
`--network=host` a los dos comandos.

Si falla un test que no tocaste, compruébalo en `origin/dev` antes de seguir: si ahí
también falla, dilo en el pull request en vez de taparlo.

### 3. Entregar

```bash
git add <solo tus archivos> && git commit -m "<qué cambia, en español>"
git fetch origin && git rebase origin/dev
git push -u origin <rama>
gh pr create --base dev --title "<título>" --body-file <archivo con qué cambia y cómo se verificó>
gh pr merge <n> --squash
git push origin --delete <rama>
cd <checkout principal> && git worktree remove ../tutor_apoe.wt/<rama> && git branch -D <rama>
```

El repositorio es **público**. Antes de subir código copiado de otro proyecto, confirma
con JP que puede publicarse.

### 4. Recetas

**Agregar o cambiar una tool del MCP** (`src/tutor/mcp_server.py`, sobre FastMCP; guía en
[`docs/mcp.md`](docs/mcp.md)):

1. Dentro de `build()`, escribe la función con `@server.tool(annotations=...)` y `@_safe`
   debajo. La anotación es una de `read_only`, `writes`, `destructive` o `calls_model`.
2. El docstring es la instrucción de uso para el modelo que la llama: di qué hace y qué devuelve.
3. La lógica va en `tutor.authoring`, `tutor.ingest`, `tutor.world` o `tutor.agent`, no en
   `mcp_server.py`. Los errores de uso se levantan con `AuthoringError(mensaje, pista)`.
4. Agrega un paso a `_selftest()` y un test en `tests/tutor/test_mcp.py`.
5. No renombres tools ni parámetros que ya existen: los clientes conectados dependen de ellos.

**Cambiar cómo se comporta el tutor** (encuadre, instrucciones, políticas): no se edita el
Markdown a mano. Se cambia en la pestaña Configuración de `tutor web` (`/wiki/`) o con la
tool `upsert_tutor` del MCP. La página es `kbs/apos/agent/agent-tutor-apos.md`;
`tutor kb build` la conserva.

**Hacer editable otro tipo de página en la wiki**: (1) declara `__authority__ = "authored"`
en su modelo de `kbs/kb_models/`; (2) agrégalo a `CONFIG_MODELS` en `src/tutor/wiki.py` y en
`superficie/src/core/tutor.ts` (tienen que calzar); (3) haz que `src/tutor/kb_build.py`
conserve su carpeta en vez de regenerarla, como hace con `agent/`; (4) recompila la interfaz;
(5) agrega un caso a `tests/tutor/test_wiki.py`. El porqué del diseño está en
[`docs/decisiones/2026-11-wiki-de-configuracion.md`](docs/decisiones/2026-11-wiki-de-configuracion.md).

**Agregar una pestaña al menú** (`src/tutor/static/app.html`): un `<button data-view="x">` en
el `<nav>`, su `<section id="panel-x">` con el `iframe`, y la vista en `descriptions` y en los
títulos del script de esa página; su ruta en `views` de `src/tutor/static/navigation.js`, para que
los enlaces entre vistas cambien de pestaña. Si la página vive en `scripts/kb.py`, agrega su
prefijo a `PAGES` o `APIS` en `src/tutor/modules.py`. Suma la vista al test
`test_el_espacio_de_trabajo_tiene_todas_las_vistas_en_un_menu`.

**Cambiar la interfaz de la wiki** (`superficie/`, React + Vite): edita, corre
`cd superficie && npm ci && npm test && npm run build` y commitea también
`src/tutor/static/wiki/`, que es lo compilado y va versionado para que funcione sin Node.

**Traer algo de otro proyecto**: copia desde un commit del origen (`git archive`), no desde
su carpeta de trabajo; deja un `ORIGEN.md` con de dónde viene, el commit y la fecha; haz un
primer commit con la copia tal cual y otro con la adaptación, para que el diff muestre solo
lo adaptado. La copia no se sincroniza con el original.

**Átomos, ramas y relaciones**: su fuente es `desk/atoms/` y se gobiernan con `deskops`;
`kbs/apos/` se genera con `tutor kb build`. No edites a mano ni `desk/` ni `kbs/apos/`.

## Interfaz de la KB

La interfaz es una sola: `tutor web` (<http://127.0.0.1:8300>), con todo en el mismo menú:
Conversación, Paquetes, Grafo APOS, Scratch, Experto, Ejemplos, Bibliografía y Configuración.
Una vista nueva se agrega ahí, como pestaña, no como una página aparte.

`scripts/kb.py` busca en los átomos fuente con `sldb find` (sin chatbot ni modelo de
lenguaje) y contiene los módulos Experto, Ejemplos y Bibliografía; `tutor web` lo lanza por
dentro y reenvía sus páginas (`src/tutor/modules.py`).

## Skills para trabajar sin programar

En `.agents/skills/` hay skills que Codex (y otros agentes) cargan solos al abrir este
repositorio. Están pensadas para quien no programa: basta pedirlo con palabras propias o
escribir `$` y el nombre.

- `tutor-preparar` — instalar y comprobar que todo funciona.
- `tutor-buscar` — qué dice la base sobre un tema, con su fuente.
- `tutor-abrir-visor` — abrir el chat y el grafo en el navegador.
- `tutor-cargar-fuente` — ingerir un PDF y proponer, revisar y aprobar átomos.
- `tutor-guardar-cambios` — guardar y publicar el trabajo.
