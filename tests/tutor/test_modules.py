"""Los módulos del visor (Experto, Ejemplos, Bibliografía) dentro de `tutor web` (`tutor.modules`)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tutor import modules, world
from tutor.web import create_app


@pytest.fixture(scope="module")
def app(kb_root: Path):
    return create_app(kb_root, model="test")


def test_sin_visor_las_paginas_lo_dicen_y_el_resto_sigue(app) -> None:
    app.state.modules = modules.Backend()
    client = TestClient(app, base_url="http://127.0.0.1")
    page = client.get("/expert")
    assert page.status_code == 503 and "no está disponible" in page.text
    assert client.get("/api/experts").status_code == 503
    assert client.get("/api/health").status_code == 200


def test_paginas_y_api_de_los_modulos_pasan_por_tutor_web(app) -> None:
    with modules.served(world.repo_root()) as viewer:
        assert viewer.error == "", viewer.error
        app.state.modules = viewer
        client = TestClient(app, base_url="http://127.0.0.1")
        for path in modules.PAGES:
            page = client.get(path)
            assert page.status_code == 200 and "text/html" in page.headers["content-type"], path
            assert "/ui/navigation.js" in page.text, path  # dentro del espacio de trabajo cambia de pestaña
        assert client.get("/expert/una-invitacion").status_code == 200  # el enlace que recibe cada especialista
        assert "questions" in client.get("/api/expert-protocol").json()
        assert client.get("/api/literature").status_code == 200
        # Otra página abierta en el mismo navegador no usa los módulos.
        assert client.get("/api/experts", headers={"Origin": "http://otro.example"}).status_code == 403
    app.state.modules = modules.Backend()


def test_fuera_de_esta_maquina_los_modulos_piden_la_clave(kb_root: Path) -> None:
    client = TestClient(create_app(kb_root, model="test", host="0.0.0.0"), base_url="http://tutor.example")
    assert client.get("/expert").status_code == 503
    assert client.get("/api/experts").status_code == 503


def test_el_espacio_de_trabajo_tiene_todas_las_vistas_en_un_menu(app) -> None:
    client = TestClient(app)
    html = client.get("/").text
    for view in ("chat", "packages", "graph", "scratch", "expert", "examples", "literature", "config"):
        assert f'data-view="{view}"' in html and f'id="panel-{view}"' in html, view
    script = client.get("/ui/navigation.js").text
    assert "'/expert': 'expert'" in script and "'/bibliografia': 'literature'" in script


def test_estilos_y_scripts_de_web(app) -> None:
    client = TestClient(app)
    assert client.get("/web/expert.css").headers["content-type"].startswith("text/css")
    assert client.get("/web/expert.js").status_code == 200
    assert client.get("/web/index.html").status_code == 404  # solo .js y .css
    assert client.get("/web/no-existe.js").status_code == 404
