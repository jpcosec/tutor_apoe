from __future__ import annotations

import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from tutor import preload
from tutor.preload_web import router


@pytest.fixture
def store(tmp_path):
    return preload.PackageStore(tmp_path / 'packages')


def outline():
    return preload.Outline(atoms=[preload.StructuralAtom(id='s1', section='Conceptos', title='Una acción requiere guía',
        answer='La acción se ejecuta paso a paso con guía externa.', source_ids=['web-c0'])])


def graph():
    return preload.Condensation(nodes=[preload.GraphNode(id='n1', title='Acción',
        answer='La acción requiere guía externa.', derived_from=['s1']),
        preload.GraphNode(id='n2', title='Guía externa', answer='La guía orienta los pasos de una acción.',
                          parent='n1', derived_from=['s1'])])


def package(store):
    return store.create('Teoría de prueba', 'https://example.org/theory',
        [{'id': 'web-c0', 'text': 'La acción requiere guía externa.'}])


def test_provenance_cycles_and_invalidation(store):
    p = package(store)
    p = store.update_outline(p, outline())
    p = store.update_graph(p, graph())
    assert preload.PackageStore(store.root).get(p['id'])['graph']
    bad = graph()
    bad.nodes[0].derived_from = ['inventado']
    with pytest.raises(ValueError, match='inexistentes'):
        store.update_graph(p, bad)
    bad = graph()
    bad.nodes[0].parent = 'n1'
    with pytest.raises(ValueError, match='ciclo'):
        store.update_graph(p, bad)
    p = store.update_outline(p, outline())
    assert p['graph'] is None and p['activated'] is None
    with pytest.raises(ValueError):
        store.get('../secret')


def test_pipeline_routes_and_activation(store, monkeypatch):
    monkeypatch.setattr(preload, 'fetch_page', lambda url: 'La acción requiere guía externa.')
    monkeypatch.setattr(preload, 'generate', lambda model, schema, instruction, data:
        outline() if schema is preload.Outline else graph())
    app = FastAPI()
    app.include_router(router('test', store))
    client = TestClient(app)
    assert client.get('/packages?embed=1').status_code == 200
    p = client.post('/api/packages/page', json={'title':'Prueba','url':'https://example.org'}).json()
    base = f'/api/packages/{p["id"]}'
    assert client.post(base+'/condense').status_code == 400
    assert client.post(base+'/activate').status_code == 400
    assert client.post(base+'/summarize').json()['outline']['atoms'][0]['id'] == 's1'
    assert client.post(base+'/condense').json()['graph']['nodes'][0]['derived_from'] == ['s1']
    result = client.post(base+'/activate')
    assert result.status_code == 200, result.text
    from pathlib import Path
    from tutor import world
    opened = world.open_kb(Path(result.json()['activated']), build_if_missing=False)
    atoms = world.list_atoms(opened)
    assert len(atoms) == 2
    assert world.parent(opened, 'atom-2')['id'] == 'atom-1'
    assert 'resumen s1' in world.get_atom(opened, atoms[0]['id'])['provenance']
    reply = client.post(base+'/chat', json={'message':'¿Qué es una acción?'})
    assert reply.status_code == 200, reply.text
    assert reply.json()['reply']
    assert client.get('/api/packages').json()[0]['title'] == 'Prueba'
    assert client.get('/api/packages/'+'a'*32).status_code == 404


def test_pdf_pages_and_empty_scan():
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    data = io.BytesIO()
    writer.write(data)
    assert preload.pdf_chunks(data.getvalue()) == []


def test_source_completeness_and_public_urls(monkeypatch):
    monkeypatch.setattr(preload.socket, 'getaddrinfo', lambda *a: [(2,1,6,'',('127.0.0.1',80))])
    with pytest.raises(ValueError, match='pública'):
        preload.public_url('http://localhost/admin')
    with pytest.raises(ValueError):
        preload.public_url('file:///etc/passwd')
    with pytest.raises(ValueError, match='cubrir'):
        preload.validate_outline(outline(), [{'id':'web-c0'}, {'id':'web-c1'}])
    parser = preload.PageText()
    parser.feed('<h1>Título</h1><script>secret()</script><p>Texto.</p>')
    assert 'secret' not in ''.join(parser.parts)
    assert 'Texto.' in ''.join(parser.parts)


def test_pdf_text_keeps_page_provenance():
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
        DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 20 200 Td (External guidance supports action.) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    data = io.BytesIO()
    writer.write(data)
    chunks = preload.pdf_chunks(data.getvalue())
    assert chunks[0]['page'] == 1
    assert chunks[0]['id'] == 'p1-c0'
    assert 'External guidance' in chunks[0]['text']
