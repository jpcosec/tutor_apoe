"""The tab workspace serves all views on one origin; the graph tab is the sldb KB graph."""
import pytest
from fastapi.testclient import TestClient

from tutor import authoring
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
    assert 'Recorrido guiado' in shell.text
    assert '/web/guided-tour.js' in shell.text
    for view, expected in [('chat', 'id="messages"'), ('packages', 'Modo tutorial'), ('scratch', 'id="scratchBody"')]:
        redirect = client.get('/' + view, follow_redirects=False)
        assert redirect.status_code == 307
        assert redirect.headers['location'] == '/#' + view
        response = client.get('/' + view + '?embed=1')
        assert response.status_code == 200 and expected in response.text
        assert '/ui/navigation.js' in response.text
        assert '/web/theme.css' in response.text
    # El grafo es el de la KB sldb (`static/graph`): se sirve directo, con o sin `embed`.
    graph = client.get('/graph?embed=1', follow_redirects=False)
    assert graph.status_code == 200 and 'mindmap.js' in graph.text
    assert client.get('/graph/static/mindmap.js').status_code == 200
    assert client.get('/ui/navigation.js').status_code == 200
    for filename in ('mindmap.js', 'hierarchy.js', 'mindmap.css', 'theme.css', 'guided-tour.js', 'tour-plans.js'):
        assert client.get('/web/' + filename).status_code == 200
    assert client.get('/web/AGENTS.md').status_code == 404


def test_graph_search_reads_the_sldb_kb(client):
    full = client.get('/api/search').json()['atoms']
    assert [a['id'] for a in full] == ['branch-workspace']
    assert client.get('/api/graph').json()['atoms'] == full
    assert client.post('/api/atoms/missing', json={'title': 'x'}).status_code == 404
    assert client.post('/api/atoms/missing/children', json={'title': 'x'}).status_code == 404
