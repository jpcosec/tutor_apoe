"""The tab workspace serves all views on one origin and delegates graph edits."""
import pytest
from fastapi.testclient import TestClient

from tutor import authoring
from tutor.graph_web import source_viewer
from tutor.web import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('TUTOR_PACKAGES_ROOT', str(tmp_path / 'packages'))
    authoring.create_kb('workspace', 'Prueba de vistas', root=tmp_path, embedder_name='hash')
    return TestClient(create_app(tmp_path / 'workspace', model='test'))


def test_shell_and_view_links(client):
    shell = client.get('/')
    assert shell.status_code == 200
    assert 'role="tablist"' in shell.text
    for view, expected in [('chat', 'id="messages"'), ('packages', 'Modo tutorial'), ('graph', 'mindmap.js')]:
        redirect = client.get('/' + view, follow_redirects=False)
        assert redirect.status_code == 307
        assert redirect.headers['location'] == '/#' + view
        response = client.get('/' + view + '?embed=1')
        assert response.status_code == 200 and expected in response.text
        assert '/ui/navigation.js' in response.text
    assert client.get('/ui/navigation.js').status_code == 200
    for filename in ('mindmap.js', 'hierarchy.js', 'mindmap.css'):
        assert client.get('/web/' + filename).status_code == 200
    assert client.get('/web/AGENTS.md').status_code == 404


def test_graph_search_and_mutations_delegate_to_source_viewer(client, monkeypatch):
    viewer = source_viewer()
    docs = viewer.atoms_by_id()
    ident = next(iter(docs))
    atom = docs[ident]
    queries, writes = [], []
    def find(query):
        queries.append(query)
        return [ident]
    def update(ident, data):
        writes.append(('update', ident, data))
        return atom
    def child(ident, data):
        writes.append(('child', ident, data))
        return atom
    monkeypatch.setattr(viewer, 'sldb_find', find)
    monkeypatch.setattr(viewer, 'update_atom', update)
    monkeypatch.setattr(viewer, 'create_child', child)
    full = client.get('/api/search').json()
    assert len(full['atoms']) == len(docs)
    filtered = client.get('/api/search', params={'q': 'topic:schema'}).json()
    assert [a['id'] for a in filtered['atoms']] == [ident]
    assert queries == ['topic:schema']
    assert client.get('/api/atoms/' + ident).json()['id'] == ident
    assert client.get('/api/atoms/missing').status_code == 404
    assert client.post('/api/atoms/' + ident, json={'title': 'Revisado'}).status_code == 200
    assert client.post('/api/atoms/' + ident + '/children', json={'title': 'Hijo'}).status_code == 201
    assert writes == [('update', ident, {'title':'Revisado'}), ('child', ident, {'title':'Hijo'})]
    def broken(query):
        raise RuntimeError('SLDB no disponible')
    monkeypatch.setattr(viewer, 'sldb_find', broken)
    assert client.get('/api/search?q=test').status_code == 503
