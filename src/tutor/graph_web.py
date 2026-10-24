"""Expose the existing source KB viewer through the tutor's local server."""
from functools import lru_cache
import importlib.util
import sys
from threading import Lock

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from tutor import world


@lru_cache(maxsize=1)
def source_viewer():
    # Keep scripts/kb.py the authority for source browsing, search and editing.
    path = world.repo_root() / 'scripts' / 'kb.py'
    spec = importlib.util.spec_from_file_location('_tutor_source_kb', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def router():
    routes = APIRouter()
    lock = Lock()
    web = world.repo_root() / 'web'

    @routes.get('/graph')
    def graph(embed: bool = False):
        if not embed:
            return RedirectResponse('/#graph')
        html = (web / 'index.html').read_text()
        return HTMLResponse(html.replace('</body>', '<script src="/ui/navigation.js"></script></body>'))

    @routes.get('/web/{filename}')
    def asset(filename: str):
        types = {'mindmap.js': 'text/javascript', 'hierarchy.js': 'text/javascript', 'mindmap.css': 'text/css', 'theme.css': 'text/css', 'guided-tour.js': 'text/javascript', 'tour-plans.js': 'text/javascript'}
        if filename not in types:
            raise HTTPException(404, 'Archivo no encontrado.')
        return FileResponse(web / filename, media_type=types[filename])

    @routes.get('/api/search')
    def search(q: str = ''):
        viewer = source_viewer()
        try:
            docs = viewer.atoms_by_id()
            ids = viewer.sldb_find(q.strip()) if q.strip() else sorted(docs)
            return {'atoms': [viewer.atom_payload(docs[ident]) for ident in ids if ident in docs]}
        except (RuntimeError, OSError) as error:
            raise HTTPException(503, str(error))

    @routes.get('/api/atoms/{ident}')
    def atom(ident: str):
        viewer = source_viewer()
        found = viewer.atoms_by_id().get(ident)
        if found is None:
            raise HTTPException(404, 'Átomo no encontrado.')
        return viewer.atom_payload(found)

    def write(operation):
        with lock:
            try:
                return {'atom': source_viewer().atom_payload(operation())}
            except KeyError as error:
                raise HTTPException(404, str(error))
            except ValueError as error:
                raise HTTPException(400, str(error))
            except (RuntimeError, OSError) as error:
                raise HTTPException(500, str(error))

    @routes.post('/api/atoms/{ident}')
    def update(ident: str, data: dict):
        return write(lambda: source_viewer().update_atom(ident, data))

    @routes.post('/api/atoms/{ident}/children', status_code=201)
    def child(ident: str, data: dict):
        return write(lambda: source_viewer().create_child(ident, data))

    return routes
