"""HTTP surface for the package workbench."""
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from tutor import preload, world
from tutor.agent import Conversation


class PageRequest(BaseModel):
    title: str
    url: str


class Message(BaseModel):
    message: str


def router(model: str, store=None):
    store = store or preload.PackageStore()
    routes = APIRouter()
    lock = Lock()
    chats = {}

    def read(ident):
        try:
            return store.get(ident)
        except FileNotFoundError:
            raise HTTPException(404, 'Paquete no encontrado.')
        except ValueError as error:
            raise HTTPException(400, str(error))

    def operation(fn):
        if not lock.acquire(blocking=False):
            raise HTTPException(409, 'Hay una operación en curso. Espera a que termine.')
        try:
            return fn()
        except HTTPException:
            raise
        except Exception as error:
            # Never include provider exceptions: SDK errors may contain request secrets.
            import logging
            logging.getLogger(__name__).warning('Precarga: %s', type(error).__name__)
            detail = str(error) if isinstance(error, ValueError) else 'La operación falló. Revisa formato, conexión y disponibilidad del modelo; el borrador anterior se conserva.'
            raise HTTPException(400, detail)
        finally:
            lock.release()

    @routes.get('/packages')
    def index():
        return FileResponse(Path(__file__).parent / 'static' / 'packages.html')

    @routes.get('/api/packages')
    def listing():
        return [{'id': p['id'], 'title': p['title']} for p in
                (store.get(f.stem) for f in sorted(store.root.glob('*.json')))]

    @routes.post('/api/packages/page')
    def page(req: PageRequest):
        def run():
            text = preload.fetch_page(req.url)
            chunks = [{'id': f'web-c{c["index"]}', **c} for c in preload.chunk_text(text, 6000)]
            return store.create(req.title, req.url, chunks)
        return operation(run)

    @routes.post('/api/packages/pdf')
    def pdf(title: str = Form(...), file: UploadFile = File(...)):
        def run():
            if not (file.filename or '').lower().endswith('.pdf'):
                raise ValueError('Selecciona un archivo PDF.')
            data = file.file.read(preload.MAX_BYTES + 1)
            if len(data) > preload.MAX_BYTES:
                raise ValueError('El PDF supera 15 MB.')
            return store.create(title, Path(file.filename).name, preload.pdf_chunks(data))
        return operation(run)

    @routes.get('/api/packages/{ident}')
    def detail(ident: str):
        return read(ident)

    @routes.post('/api/packages/{ident}/summarize')
    def summarize(ident: str):
        def run():
            package = read(ident)
            return store.update_outline(package, preload.summarize(package, model))
        return operation(run)

    @routes.put('/api/packages/{ident}/outline')
    def outline(ident: str, value: preload.Outline):
        return operation(lambda: store.update_outline(read(ident), value))

    @routes.post('/api/packages/{ident}/condense')
    def condense(ident: str):
        def run():
            package = read(ident)
            if not package['outline']:
                raise ValueError('Primero genera y revisa el resumen estructural.')
            return store.update_graph(package, preload.condense(package, model))
        return operation(run)

    @routes.put('/api/packages/{ident}/graph')
    def graph(ident: str, value: preload.Condensation):
        return operation(lambda: store.update_graph(read(ident), value))

    @routes.post('/api/packages/{ident}/activate')
    def activate(ident: str):
        def run():
            package = read(ident)
            if not package['graph']:
                raise ValueError('Primero condensa y revisa el grafo.')
            if not package['activated']:
                preload.activate(store, package)
            return package
        return operation(run)

    @routes.post('/api/packages/{ident}/chat')
    def chat(ident: str, req: Message):
        def run():
            package = read(ident)
            if not package['activated']:
                raise ValueError('Activa el paquete antes de conversar.')
            key = (ident, package['activated'])
            if key not in chats:
                chats[key] = Conversation(kb=world.open_kb(Path(package['activated']), build_if_missing=False), model=model)
            result = chats[key].ask(req.message)
            return {'reply': result.reply, 'mesa': result.mesa}
        return operation(run)

    return routes
