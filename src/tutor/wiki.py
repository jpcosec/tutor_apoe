"""La wiki de configuración del tutor: las páginas `AgentDoc` de la KB, vistas y editadas en el navegador.

    tutor web --kb kbs/apos            # la pestaña Configuración, o directo en /wiki/

La interfaz es la superficie de sldb compilada (`superficie/` → `static/wiki/`). No habla con sldb:
`tutor web` lanza el `sldb serve` de la KB solo para esta máquina, con un token de un solo uso, y lo
expone en `/api/wiki/…`. Por ahí pasan las lecturas y, de las escrituras, solo `POST save` con cambios
(`update`) sobre páginas de los modelos de `CONFIG_MODELS`. Lo demás de la KB (átomos, ramas, relaciones)
se genera desde `desk/atoms/` y aquí se lee.

Tras cada guardado se reabre la KB, así el turno siguiente del tutor ya usa el texto nuevo. Si con el
cambio la KB deja de validar o el rol se queda sin página, el guardado se deshace y se dice por qué.

Acceso: sin clave solo cuando el servidor escucha en loopback. Con `TUTOR_WIKI_KEY` (16 caracteres o
más) se exige siempre, por HTTP Basic (cualquier usuario, la clave como contraseña) o Bearer; si el
servidor escucha en otra interfaz y no hay clave, la wiki responde 503 y dice qué falta.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import hmac
import http.client
import ipaddress
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

#: Los modelos cuyas páginas son configuración y se editan desde la wiki. Tiene que calzar con
#: `CONFIG_MODELS` de `superficie/src/core/tutor.ts` (lo que la interfaz muestra como editable).
CONFIG_MODELS = frozenset({"AgentDoc"})
KEY_ENV = "TUTOR_WIKI_KEY"
MIN_KEY = 16
SAVE = "save"
UI = Path(__file__).parent / "static" / "wiki"
REBUILD = "cd superficie && npm ci && npm run build"
#: Segundos que se le dan al `sldb serve` para responder, y para terminar por las buenas al cerrar.
START_TIMEOUT = 30.0
STOP_TIMEOUT = 5.0
_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,159}$")
_LOCAL_NAMES = {"localhost"}


@dataclass(frozen=True)
class Backend:
    """Dónde quedó el `sldb serve` de la KB, o por qué no hay (`error`)."""

    url: str = ""
    token: str = ""
    error: str = "Este servidor no lanzó el `sldb serve` de la base: la wiki se abre con `tutor web`."


# -- qué pasa por el proxy --------------------------------------------------------------


def allowed(method: str, route: str) -> bool:
    """Las lecturas pasan todas; de las escrituras, solo el guardado de páginas."""
    return method == "GET" or (method == "POST" and route.strip("/") == SAVE)


def save_objection(body: bytes, model_of: Callable[[str], str | None]) -> str | None:
    """Por qué este guardado no se reenvía a sldb, en palabras; None si se puede.

    Solo pasan cambios (`update`) sobre páginas que ya existen y son de un modelo de configuración.
    `model_of` dice de qué modelo es hoy una página (None si no existe): no se le cree al pedido."""
    try:
        request = json.loads(body or b"{}")
    except ValueError:
        return "El guardado no se entiende: se esperaba JSON."
    changes = request.get("changes") if isinstance(request, dict) else None
    if not isinstance(changes, list) or not changes:
        return "Desde la wiki del tutor se guarda con una lista de cambios (`changes`); otra forma de guardar no pasa por aquí."
    for change in changes:
        if not isinstance(change, dict) or not isinstance(change.get("id"), str) or not _ID.fullmatch(change["id"]):
            return "Cada cambio tiene que nombrar una página por su identificador."
        name, action = change["id"], change.get("action")
        model = model_of(name)
        if model not in CONFIG_MODELS:
            what = f"«{name}» es una página de tipo {model}" if model else f"«{name}» no es una página de configuración de esta base"
            return (
                f"{what}: desde la wiki solo se cambia la configuración del tutor ({', '.join(sorted(CONFIG_MODELS))}). "
                "Los átomos, ramas y relaciones se generan desde desk/atoms/ y se cambian ahí, con deskops."
            )
        if action != "update":
            return (
                f"Desde la wiki se cambia el contenido de «{name}», pero no se crea, se quita ni se mueve "
                f"(se pidió `{action}`): las páginas de configuración las siembra `tutor kb build`."
            )
    return None


# -- acceso -----------------------------------------------------------------------------


def is_loopback(host: str) -> bool:
    """¿Escuchar en `host` deja el servidor alcanzable solo desde esta máquina?"""
    name = host.strip("[]").lower()
    if name in _LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def _presented(request: Request) -> str:
    """La clave que trae el pedido: Bearer, o la contraseña de Basic (el usuario da igual)."""
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer":
        return value.strip()
    if scheme.lower() == "basic":
        try:
            return base64.b64decode(value.strip(), validate=True).decode("utf-8").partition(":")[2]
        except (binascii.Error, UnicodeDecodeError):
            return ""
    return ""


def access_error(request: Request, *, loopback: bool, key: str) -> Response | None:
    """La respuesta que corresponde si este pedido no puede entrar a la wiki; None si puede."""
    host = urlsplit(f"//{request.headers.get('host', '')}").hostname or ""
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host", ""):
        # Otra página web abierta en este navegador no lee ni escribe la configuración del tutor.
        return JSONResponse({"ok": False, "error": "La wiki solo se usa desde su propia página, no desde otro sitio."}, status_code=403)
    if not key:
        if not loopback:
            return _unavailable(
                "La wiki de configuración está cerrada: este servidor escucha fuera de esta máquina y no tiene clave. "
                f"Define {KEY_ENV} ({MIN_KEY} caracteres o más) antes de `tutor web`, o lánzalo con --host 127.0.0.1."
            )
        if not is_loopback(host):  # un nombre ajeno que resuelve a esta máquina (DNS rebinding)
            return JSONResponse({"ok": False, "error": "Sin clave, la wiki solo se abre como http://127.0.0.1 o http://localhost."}, status_code=403)
        return None
    if len(key) < MIN_KEY:
        return _unavailable(f"La wiki de configuración está cerrada: {KEY_ENV} tiene menos de {MIN_KEY} caracteres.")
    if not hmac.compare_digest(_presented(request).encode("utf-8"), key.encode("utf-8")):
        return JSONResponse(
            {"ok": False, "error": f"Falta la clave de la wiki ({KEY_ENV}) o no es la correcta."},
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Configuracion del tutor", charset="UTF-8"'},
        )
    return None


def _unavailable(message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=503)


# -- el `sldb serve` de la KB -----------------------------------------------------------


def serve_command(kb_root: Path, port: int) -> list[str]:
    from tutor import world
    from tutor.authoring import KbWriter

    pythonpath = KbWriter(kb_root).pythonpath  # absoluto: `serve` hace chdir antes de resolverlo
    return [sys.executable, "-m", "sldb", "serve", "--store", str(kb_root / world.STORE_DIR), "--pythonpath", pythonpath, "--host", "127.0.0.1", "--port", str(port)]


def _wait(child: subprocess.Popen, url: str, token: str, timeout: float) -> str | None:
    """None cuando el hijo responde con su token; si no, por qué no. El puerto se eligió antes de que el
    hijo lo tomara: solo una respuesta que acepta este token prueba que quien atiende ahí es él."""
    request = urllib.request.Request(f"{url}/health", headers={"Authorization": f"Bearer {token}"})
    limit = time.monotonic() + timeout
    while True:
        if child.poll() is not None:
            return f"`sldb serve` terminó al arrancar, con código {child.returncode}. Revisa la base con `tutor kb validate`."
        try:
            # `/health` revisa el store entero: en una KB de mil páginas tarda un par de segundos
            with urllib.request.urlopen(request, timeout=max(1.0, limit - time.monotonic())) as response:
                if response.status == 200:
                    return None
        except (OSError, http.client.HTTPException):  # todavía no escucha, o respondió otro
            pass
        if time.monotonic() >= limit:
            return f"`sldb serve` no respondió en {timeout:g} segundos."
        time.sleep(0.1)


def _stop(child: subprocess.Popen) -> None:
    """Termina al hijo y lo recoge; si no hace caso, lo mata: no queda un `sldb serve` suelto."""
    if child.poll() is None:
        child.terminate()
    try:
        child.wait(timeout=STOP_TIMEOUT)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


@contextlib.contextmanager
def served(kb_root: Path | str, *, command: Callable[[Path, int], list[str]] = serve_command, timeout: float = START_TIMEOUT) -> Iterator[Backend]:
    """Levanta el `sldb serve` de la KB mientras dura el bloque y entrega dónde quedó, ya respondiendo.

    Escucha solo en 127.0.0.1 y con un token de un solo uso que no sale de este proceso. Si no arranca,
    no falla: entrega un `Backend` con el motivo, y el resto de `tutor web` sigue funcionando."""
    root = Path(kb_root).resolve()
    with socket.socket() as free:
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
    token = secrets.token_urlsafe(24)
    url = f"http://127.0.0.1:{port}"
    # `SLDB_ACTOR` es quien firma lo guardado en el bloque `sldb:` de cada página.
    env = {"SLDB_ACTOR": "tutor wiki", **os.environ, "SLDB_SERVE_TOKEN": token}
    try:
        child = subprocess.Popen(command(root, port), env=env, stdout=subprocess.DEVNULL)
    except OSError as error:
        yield Backend(error=f"No se pudo lanzar `sldb serve`: {error}")
        return
    try:
        problem = _wait(child, url, token, timeout)
        if problem:
            _stop(child)
            print(f"! La wiki de configuración no está disponible: {problem}", file=sys.stderr)
            yield Backend(error=problem)
        else:
            yield Backend(url=url, token=token, error="")
    finally:
        _stop(child)


def forget_store_reads(store: Path) -> None:
    """El store lo acaba de escribir otro proceso (`sldb serve`). sldb recuerda en memoria las entradas
    de documentos de cada modelo y solo las contrasta con el disco al empezar una operación nueva; sin
    esto, la primera validación en este proceso compara el Markdown nuevo con los hashes viejos y da
    la KB por inválida (`hash_c no calza`) aunque en disco esté íntegra."""
    try:
        from sldb.store import documents_hash
    except ImportError:  # otra versión de sldb: sin esa memoria no hay nada que olvidar
        return
    documents_hash.new_operation(store)


# -- rutas ------------------------------------------------------------------------------


def _page(title: str, body: str, status: int) -> HTMLResponse:
    html = (
        '<!doctype html><html lang="es"><meta charset="utf-8"><title>Configuración del tutor</title>'
        '<body style="font:15px/1.6 system-ui,sans-serif;color:#243a35;background:#f5f5ef;max-width:44rem;margin:12vh auto;padding:0 1.5rem">'
        f"<h1 style=\"font:26px Georgia,serif;color:#236650\">{escape(title)}</h1>{body}</body></html>"
    )
    return HTMLResponse(html, status_code=status)


def router(
    backend: Callable[[], Backend],
    *,
    host: str,
    model_of: Callable[[str], str | None],
    after_save: Callable[[], str | None],
) -> APIRouter:
    """Las rutas de la wiki: la interfaz en `/wiki/` y la API de sldb en `/api/wiki/…`.

    `backend()` entrega el `sldb serve` vigente; `model_of(id)` el modelo de una página; `after_save()`
    pone al día al tutor tras un guardado y devuelve por qué no pudo, si no pudo."""
    import asyncio

    api = APIRouter()
    loopback = is_loopback(host)
    key = os.environ.get(KEY_ENV, "")
    saving = asyncio.Lock()

    def denied(request: Request) -> Response | None:
        return access_error(request, loopback=loopback, key=key)

    @api.get("/wiki", include_in_schema=False)
    def wiki_root():
        return RedirectResponse("/wiki/")

    @api.get("/wiki/{path:path}", include_in_schema=False)
    def wiki_ui(path: str, request: Request):
        if (refused := denied(request)) is not None:
            if refused.status_code == 503:  # dicho como página: es lo que ve quien abre la pestaña
                return _page("La wiki de configuración está cerrada", f"<p>{escape(json.loads(refused.body)['error'])}</p>", 503)
            return refused
        if path in ("", "index.html"):
            if not (UI / "index.html").is_file():
                return _page(
                    "Falta la interfaz de la wiki",
                    f"<p>No está la interfaz compilada en <code>{escape(str(UI))}</code>. Viene versionada con el repositorio; "
                    f"si se borró, se recompila (hace falta Node) con:</p><pre>{escape(REBUILD)}</pre>"
                    "<p>El resto del tutor sigue funcionando.</p>",
                    503,
                )
            if problem := backend().error:
                return _page(
                    "La wiki de configuración no está disponible",
                    f"<p>{escape(problem)}</p><p>El resto del tutor sigue funcionando. La configuración también se lee y se cambia con "
                    "<code>sldb fields show</code> y <code>sldb fields update</code> sobre la base.</p>",
                    503,
                )
            return FileResponse(UI / "index.html", media_type="text/html", headers={"Cache-Control": "no-cache"})
        target = (UI / path).resolve()
        if not target.is_relative_to(UI.resolve()) or not target.is_file():
            return JSONResponse({"ok": False, "error": "No existe."}, status_code=404)
        return FileResponse(target)

    async def forward(method: str, url: str, token: str, *, params: dict[str, str] | None = None, content: bytes = b"", content_type: str | None = None) -> httpx.Response | None:
        headers = {"Authorization": f"Bearer {token}"}
        if content_type:
            headers["Content-Type"] = content_type
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                return await client.request(method, url, params=params, content=content, headers=headers)
        except httpx.HTTPError:
            return None

    async def undo(target: Backend, changes: list[dict[str, Any]]) -> bool:
        """Devuelve cada página a lo que tenía antes del guardado (su `expected`)."""
        if not all(isinstance(c.get("expected"), dict) and isinstance(c.get("payload"), dict) for c in changes):
            return False
        back = [{**c, "payload": c["expected"], "expected": c["payload"]} for c in changes]
        body = json.dumps({"changes": back}).encode("utf-8")
        response = await forward("POST", f"{target.url}/{SAVE}", target.token, content=body, content_type="application/json")
        return response is not None and response.status_code == 200

    @api.api_route("/api/wiki/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    async def wiki_api(rest: str, request: Request):
        """La API de sldb de la KB. No interpreta las lecturas: las reenvía y devuelve la respuesta tal cual."""
        if (refused := denied(request)) is not None:
            return refused
        if not allowed(request.method, rest):
            return JSONResponse({"ok": False, "error": "Desde la wiki del tutor se leen páginas y se guarda su contenido; los tipos de página y el resto del store no se cambian aquí."}, status_code=403)
        target = backend()
        if target.error:
            return _unavailable(f"La wiki de configuración no está disponible: {target.error}")
        body = await request.body()
        url = f"{target.url}/{rest}"

        def relay(response: httpx.Response | None) -> Response:
            if response is None:
                return JSONResponse({"ok": False, "error": "No se pudo llegar al `sldb serve` de la base."}, status_code=502)
            return Response(response.content, status_code=response.status_code, media_type=response.headers.get("content-type"))

        if request.method == "GET":
            return relay(await forward("GET", url, target.token, params=dict(request.query_params)))
        async with saving:  # revisar, guardar y poner al día al tutor es un solo paso
            if objection := save_objection(body, model_of):
                return JSONResponse({"ok": False, "error": objection}, status_code=403)
            response = await forward("POST", url, target.token, content=body, content_type=request.headers.get("content-type"))
            if response is None or response.status_code != 200:
                return relay(response)
            if problem := await run_in_threadpool(after_save):
                undone = await undo(target, json.loads(body)["changes"])
                if undone:
                    await run_in_threadpool(after_save)
                tail = "El cambio se deshizo: el tutor sigue con el texto anterior." if undone else "El cambio quedó escrito y no se pudo deshacer: corrígelo antes del próximo turno."
                return JSONResponse({"ok": False, "error": f"Con este cambio el tutor no puede seguir: {problem} {tail}"}, status_code=422)
            return relay(response)

    return api


__all__ = ["CONFIG_MODELS", "KEY_ENV", "Backend", "access_error", "allowed", "is_loopback", "router", "save_objection", "served"]
