"""Los módulos del visor (`scripts/kb.py`) dentro de `tutor web`: Experto, Ejemplos y Bibliografía.

    tutor web --kb kbs/apos            # pestañas Experto, Ejemplos y Bibliografía

Esos módulos viven en `scripts/kb.py` y `web/` (sus páginas, su API y sus datos en `.local/`). Aquí no
se reimplementan: `tutor web` lanza ese mismo visor solo para esta máquina, en un puerto libre, y
reenvía sus páginas y su API. Lo que se agregue a un módulo en `kb.py` vale aquí sin tocar nada; un
módulo nuevo necesita su prefijo en `PAGES`/`APIS` y su pestaña en `static/app.html`.

Acceso: el de la wiki de configuración (`tutor.wiki.access_error`). Sin clave solo en loopback; el
visor original tampoco se abre fuera de la máquina.
"""

from __future__ import annotations

import contextlib
import http.client
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from html import escape
from pathlib import Path

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from tutor import wiki

#: Páginas del visor que se reenvían (la ruta exacta o cualquier cosa debajo de ella).
PAGES = ("/expert", "/examples", "/bibliografia", "/visualizations/matrix-vector")
#: Prefijos de su API. `/api/search` y `/api/atoms` NO: en `tutor web` son las de la KB sldb.
APIS = ("/api/expert-protocol", "/api/expert-module", "/api/experts", "/api/examples-protocol", "/api/examples", "/api/literature")
SCRIPT = Path("scripts") / "kb.py"
START_TIMEOUT = 30.0
STOP_TIMEOUT = 5.0
#: Con esto una página reenviada, abierta dentro del espacio de trabajo, cambia de pestaña en vez de
#: cargar otra vista dentro de la suya (ver `static/navigation.js`). Fuera de un iframe no hace nada.
NAVIGATION = b'<script src="/ui/navigation.js"></script>'


@dataclass(frozen=True)
class Backend:
    """Dónde quedó el visor de módulos, o por qué no hay (`error`)."""

    url: str = ""
    error: str = "Este servidor no lanzó el visor de módulos: se abre con `tutor web`."


def serve_command(repo: Path, port: int) -> list[str]:
    return [sys.executable, str(repo / SCRIPT), "serve", "--port", str(port)]


def _wait(child: subprocess.Popen, url: str, timeout: float) -> str | None:
    """None cuando el visor ya responde; si no, por qué no."""
    limit = time.monotonic() + timeout
    while True:
        if child.poll() is not None:
            return f"`{SCRIPT} serve` terminó al arrancar, con código {child.returncode}."
        try:
            with urllib.request.urlopen(f"{url}/api/expert-protocol", timeout=2) as response:
                if response.status == 200:
                    return None
        except (OSError, http.client.HTTPException):
            pass
        if time.monotonic() >= limit:
            return f"`{SCRIPT} serve` no respondió en {timeout:g} segundos."
        time.sleep(0.1)


def _stop(child: subprocess.Popen) -> None:
    if child.poll() is None:
        child.terminate()
    try:
        child.wait(timeout=STOP_TIMEOUT)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


@contextlib.contextmanager
def served(repo: Path | str, *, command: Callable[[Path, int], list[str]] = serve_command, timeout: float = START_TIMEOUT) -> Iterator[Backend]:
    """Levanta el visor de módulos mientras dura el bloque. Si no arranca no falla: entrega el motivo
    y el resto de `tutor web` sigue funcionando."""
    root = Path(repo).resolve()
    if not (root / SCRIPT).is_file():
        yield Backend(error=f"No está `{SCRIPT}` en {root}: los módulos Experto, Ejemplos y Bibliografía vienen con el repositorio.")
        return
    with socket.socket() as free:
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    try:
        child = subprocess.Popen(command(root, port), cwd=root, stdout=subprocess.DEVNULL)
    except OSError as error:
        yield Backend(error=f"No se pudo lanzar el visor de módulos: {error}")
        return
    try:
        problem = _wait(child, url, timeout)
        if problem:
            _stop(child)
            print(f"! Los módulos Experto, Ejemplos y Bibliografía no están disponibles: {problem}", file=sys.stderr)
            yield Backend(error=problem)
        else:
            yield Backend(url=url, error="")
    finally:
        _stop(child)


def _unavailable_page(message: str) -> HTMLResponse:
    html = (
        '<!doctype html><html lang="es"><meta charset="utf-8"><title>Módulo no disponible</title>'
        '<body style="font:15px/1.6 system-ui,sans-serif;color:#243a35;background:#f5f5ef;max-width:44rem;margin:12vh auto;padding:0 1.5rem">'
        f'<h1 style="font:26px Georgia,serif;color:#236650">Este módulo no está disponible</h1><p>{escape(message)}</p>'
        "<p>El resto del tutor sigue funcionando.</p></body></html>"
    )
    return HTMLResponse(html, status_code=503)


def router(backend: Callable[[], Backend], *, host: str) -> APIRouter:
    """Las rutas de los módulos: sus páginas y su API, reenviadas al visor vigente (`backend()`)."""
    import os

    api = APIRouter()
    loopback = wiki.is_loopback(host)
    key = os.environ.get(wiki.KEY_ENV, "")

    async def forward(request: Request) -> Response:
        is_page = not request.url.path.startswith("/api/")
        if (refused := wiki.access_error(request, loopback=loopback, key=key)) is not None:
            return refused
        target = backend()
        if target.error:
            return _unavailable_page(target.error) if is_page else JSONResponse({"error": target.error}, status_code=503)
        headers = {}
        if content_type := request.headers.get("content-type"):
            headers["Content-Type"] = content_type
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.request(
                    request.method, f"{target.url}{request.url.path}", params=dict(request.query_params), content=await request.body(), headers=headers
                )
        except httpx.HTTPError:
            message = "No se pudo llegar al visor de módulos."
            return _unavailable_page(message) if is_page else JSONResponse({"error": message}, status_code=502)
        content, media_type = response.content, response.headers.get("content-type")
        if is_page and "text/html" in (media_type or "") and b"</body>" in content:
            content = content.replace(b"</body>", NAVIGATION + b"</body>", 1)
        passed = {name: response.headers[name] for name in ("content-disposition",) if name in response.headers}
        return Response(content, status_code=response.status_code, media_type=media_type, headers=passed)

    methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]
    for prefix in (*PAGES, *APIS):
        api.add_api_route(prefix, forward, methods=methods, include_in_schema=False)
        api.add_api_route(prefix + "/{rest:path}", forward, methods=methods, include_in_schema=False)
    return api


__all__ = ["APIS", "PAGES", "Backend", "router", "served"]
