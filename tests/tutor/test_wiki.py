"""La wiki de configuración (`tutor.wiki`): qué deja pasar el proxy, quién entra, qué conserva `kb_build`
y, de punta a punta, que lo guardado en la wiki vale desde el turno siguiente. Sin red ni navegador:
un `sldb serve` real sobre una KB temporal y el modelo `test`."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tutor import agent as agent_mod
from tutor import authoring, kb_build, wiki, world
from tutor.web import create_app

KB = "demo"
AGENT = f"agent-tutor-{KB}"
ATOM = "atom-uno"
LOCAL = "http://127.0.0.1:8300"
KEY = "clave-de-la-wiki-de-prueba"


# -- el filtro del proxy --------------------------------------------------------------------


def _models(name: str) -> str | None:
    return {AGENT: "AgentDoc", ATOM: "KnowledgeAtom", "branch-demo": "BranchNode"}.get(name)


def _save(*changes: dict) -> bytes:
    return json.dumps({"changes": list(changes)}).encode()


def test_por_el_proxy_pasan_las_lecturas_y_solo_el_guardado() -> None:
    assert wiki.allowed("GET", "schema") and wiki.allowed("GET", "document/segments") and wiki.allowed("GET", "models/detail")
    assert wiki.allowed("POST", "save") and wiki.allowed("POST", "/save/")
    for method, route in [("POST", "models/promote"), ("POST", "models/fields-add"), ("POST", "docs"), ("POST", "edges/rewrite"), ("DELETE", "document"), ("PUT", "save"), ("PATCH", "save")]:
        assert not wiki.allowed(method, route), (method, route)


def test_solo_se_guardan_cambios_sobre_paginas_de_configuracion() -> None:
    assert wiki.save_objection(_save({"id": AGENT, "action": "update", "model": "AgentDoc", "payload": {}}), _models) is None
    # Un átomo, aunque el pedido diga que es un AgentDoc: manda el modelo que la página tiene hoy.
    for change in [
        {"id": ATOM, "action": "update", "model": "KnowledgeAtom", "payload": {}},
        {"id": ATOM, "action": "update", "model": "AgentDoc", "payload": {}},
        {"id": ATOM, "action": "delete", "model": "KnowledgeAtom"},
        {"id": "branch-demo", "action": "move", "path": "x.md"},
        {"id": "atom-nuevo", "action": "create", "model": "KnowledgeAtom", "payload": {}},
        {"id": "otro-agente", "action": "create", "model": "AgentDoc", "payload": {}},
        {"id": "ajeno", "action": "track", "path": "/etc/hostname"},
    ]:
        objection = wiki.save_objection(_save(change), _models)
        assert objection and "solo se cambia la configuración del tutor" in objection, change
    assert "KnowledgeAtom" in wiki.save_objection(_save({"id": ATOM, "action": "update", "payload": {}}), _models)
    # La página de configuración se cambia, no se quita ni se mueve.
    for action in ("delete", "move", "untrack", "create"):
        assert "no se crea, se quita ni se mueve" in wiki.save_objection(_save({"id": AGENT, "action": action}), _models)
    # Un cambio bueno no blanquea a los demás del mismo lote.
    mixed = _save({"id": AGENT, "action": "update", "payload": {}}, {"id": ATOM, "action": "update", "payload": {}})
    assert wiki.save_objection(mixed, _models)


def test_un_guardado_sin_lista_de_cambios_o_mal_formado_no_pasa() -> None:
    single = json.dumps({"id": AGENT, "model": "AgentDoc", "payload": {}}).encode()  # el guardado de un solo documento de sldb
    for body in [single, b"", b"{}", b"no es json", b"[]", _save(), _save("x"), _save({"action": "update"}), _save({"id": 3, "action": "update"}), _save({"id": f"AgentDoc:{AGENT}", "action": "update"})]:
        assert wiki.save_objection(body, _models), body


# -- acceso ---------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def kbs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("wiki-kbs")
    authoring.create_kb(KB, "Demo", root=base)
    authoring.upsert_atom(KB, {"id": ATOM, "title": "Uno", "question": "what", "answer": "Uno es uno.", "provenance": "test", "parent": "branch-demo"}, base)
    return base


@pytest.fixture(scope="module")
def backend(kbs: Path):
    """El `sldb serve` de la KB de prueba, como lo deja `tutor web`."""
    with wiki.served(kbs / KB) as served:
        assert not served.error, served.error
        yield served


def _app(kbs: Path, backend: wiki.Backend | None, host: str = "127.0.0.1"):
    app = create_app(kbs / KB, model="test", host=host)
    if backend is not None:
        app.state.wiki = backend
    return app


def _basic(password: str, user: str = "quien-sea") -> dict[str, str]:
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


def test_en_loopback_la_wiki_se_abre_sin_clave(kbs: Path, backend: wiki.Backend, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(wiki.KEY_ENV, raising=False)
    api = TestClient(_app(kbs, backend), base_url=LOCAL)
    page = api.get("/wiki/")
    assert page.status_code == 200 and "/wiki/assets/" in page.text
    assert api.get("/wiki", follow_redirects=False).headers["location"] == "/wiki/"
    assert {m["id"] for m in api.get("/api/wiki/schema").json()["models"]} >= {"AgentDoc", "KnowledgeAtom"}
    assert api.get("/wiki/../app.html").status_code == 404 and api.get("/wiki/no-existe.js").status_code == 404
    # Otra página web del mismo navegador, o un nombre ajeno que resuelve a esta máquina, no entran.
    assert api.get("/api/wiki/schema", headers={"Origin": "http://otro.example"}).status_code == 403
    assert api.post("/api/wiki/save", json={"changes": []}, headers={"Origin": "http://otro.example"}).status_code == 403
    assert TestClient(_app(kbs, backend), base_url="http://otro.example:8300").get("/api/wiki/schema").status_code == 403
    assert TestClient(_app(kbs, backend), base_url="http://localhost:8300").get("/api/wiki/schema").status_code == 200


def test_fuera_de_loopback_sin_clave_la_wiki_esta_cerrada_y_dice_por_que(kbs: Path, backend: wiki.Backend, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(wiki.KEY_ENV, raising=False)
    api = TestClient(_app(kbs, backend, host="0.0.0.0"), base_url="http://tutor.example")
    for path in ("/wiki/", "/wiki/assets/x.js", "/api/wiki/schema"):
        closed = api.get(path)
        assert closed.status_code == 503 and wiki.KEY_ENV in closed.text, path
    assert api.post("/api/wiki/save", json={"changes": []}).status_code == 503
    assert api.get("/").status_code == 200 and api.get("/api/health").json()["ok"]  # el resto sigue abierto, como antes
    monkeypatch.setenv(wiki.KEY_ENV, "corta")
    short = TestClient(_app(kbs, backend, host="0.0.0.0"), base_url="http://tutor.example").get("/api/wiki/schema", headers=_basic("corta"))
    assert short.status_code == 503 and "menos de 16" in short.json()["error"]


def test_fuera_de_loopback_se_entra_con_la_clave_por_basic_o_bearer(kbs: Path, backend: wiki.Backend, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(wiki.KEY_ENV, KEY)
    api = TestClient(_app(kbs, backend, host="0.0.0.0"), base_url="http://tutor.example")
    for path in ("/wiki/", "/api/wiki/schema"):
        refused = api.get(path)
        assert refused.status_code == 401 and refused.headers["www-authenticate"].startswith("Basic"), path
        assert api.get(path, headers=_basic("otra-clave-cualquiera")).status_code == 401
        assert api.get(path, headers={"Authorization": "Bearer otra-clave-cualquiera"}).status_code == 401
        assert api.get(path, headers={"Authorization": "Basic %%%"}).status_code == 401
        assert api.get(path, headers=_basic(KEY)).status_code == 200
        assert api.get(path, headers=_basic(KEY, user="")).status_code == 200
        assert api.get(path, headers={"Authorization": f"Bearer {KEY}"}).status_code == 200
    assert api.post("/api/wiki/save", json={"changes": []}).status_code == 401
    # Con clave definida se pide también en loopback.
    local = TestClient(_app(kbs, backend), base_url=LOCAL)
    assert local.get("/api/wiki/schema").status_code == 401 and local.get("/api/wiki/schema", headers=_basic(KEY)).status_code == 200


def test_el_sldb_serve_solo_responde_con_su_token(backend: wiki.Backend) -> None:
    import httpx

    assert backend.url.startswith("http://127.0.0.1:")
    assert httpx.get(f"{backend.url}/schema").status_code == 401
    assert httpx.get(f"{backend.url}/schema", headers={"Authorization": f"Bearer {backend.token}"}).status_code == 200


# -- cuando falta algo ----------------------------------------------------------------------


def test_sin_la_interfaz_compilada_el_tutor_sigue_y_la_wiki_dice_que_falta(kbs: Path, backend: wiki.Backend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(wiki.KEY_ENV, raising=False)
    monkeypatch.setattr(wiki, "UI", tmp_path / "no-compilada")
    api = TestClient(_app(kbs, backend), base_url=LOCAL)
    missing = api.get("/wiki/")
    assert missing.status_code == 503 and "npm run build" in missing.text and "Falta la interfaz" in missing.text
    assert api.get("/").status_code == 200 and api.get("/api/health").json()["ok"]
    assert api.get("/api/wiki/schema").status_code == 200  # el proxy no depende de la interfaz


def test_si_sldb_serve_no_arranca_el_tutor_sigue_y_la_wiki_lo_dice(kbs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(wiki.KEY_ENV, raising=False)
    with wiki.served(kbs / KB, command=lambda root, port: [sys.executable, "-c", "raise SystemExit(3)"]) as broken:
        assert "código 3" in broken.error and not broken.url
        api = TestClient(_app(kbs, broken), base_url=LOCAL)
        page = api.get("/wiki/")
        assert page.status_code == 503 and "código 3" in page.text
        down = api.get("/api/wiki/schema")
        assert down.status_code == 503 and "código 3" in down.json()["error"]
        assert api.post("/api/chat", json={"message": "¿qué es uno?"}).status_code == 200
    with wiki.served(kbs / KB, command=lambda root, port: ["/no/existe/sldb"]) as absent:
        assert "No se pudo lanzar" in absent.error
    # Sin `tutor web` (la app creada a mano, sin lanzar nada) también lo dice.
    alone = TestClient(_app(kbs, None), base_url=LOCAL).get("/api/wiki/schema")
    assert alone.status_code == 503 and "tutor web" in alone.json()["error"]


def test_la_interfaz_compilada_viene_en_el_paquete() -> None:
    """Quien usa el tutor no tiene Node: `static/wiki/` va versionada y completa."""
    import re

    index = (wiki.UI / "index.html").read_text(encoding="utf-8")
    assets = re.findall(r'(?:src|href)="/wiki/(assets/[^"]+)"', index)
    assert assets and all((wiki.UI / asset).is_file() for asset in assets), assets
    script = next(a for a in assets if a.endswith(".js"))
    assert '"/api/wiki"' in (wiki.UI / script).read_text(encoding="utf-8")  # habla con el proxy, no con sldb


# -- de punta a punta -----------------------------------------------------------------------


@pytest.fixture()
def echo_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """El modelo `test` responde con las instrucciones que recibió: así se ve qué texto usó el turno."""
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    def echo(messages, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(info.instructions or "")])

    monkeypatch.setattr(agent_mod, "_test_model", lambda mesa: FunctionModel(echo))


def _page(api: TestClient, name: str) -> dict:
    found = api.get("/api/wiki/document/segments", params={"id": name})
    assert found.status_code == 200, found.text
    return found.json()


def _update(api: TestClient, page: dict, **fields):
    change = {"id": page["doc"], "action": "update", "model": page["model"], "payload": {**page["payload"], **fields}, "expected": page["payload"]}
    return api.post("/api/wiki/save", json={"changes": [change]})


def test_lo_guardado_en_la_wiki_vale_desde_el_turno_siguiente(kbs: Path, backend: wiki.Backend, echo_model: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(wiki.KEY_ENV, raising=False)
    api = TestClient(_app(kbs, backend), base_url=LOCAL)
    agent_page = _page(api, AGENT)
    assert agent_page["model"] == "AgentDoc"
    assert api.get("/api/wiki/models/detail", params={"model": "AgentDoc"}).json()["model"]["authority"] == "authored"
    assert api.get("/api/wiki/models/detail", params={"model": "KnowledgeAtom"}).json()["model"]["authority"] == "generated"
    before = agent_page["payload"]["framing"]

    first = api.post("/api/chat", json={"message": "¿qué es uno?"}).json()
    assert before in first["turn"]["assistant_message"]

    # Un átomo se ve, pero no se cambia: el servidor lo rechaza aunque la interfaz ya lo muestre en solo lectura.
    atom_page = _page(api, ATOM)
    atom_file = kbs / KB / atom_page["path"]
    atom_text = atom_file.read_text(encoding="utf-8")
    refused = _update(api, atom_page, title="Cambiado por la wiki")
    assert refused.status_code == 403 and "KnowledgeAtom" in refused.json()["error"] and "desk/atoms" in refused.json()["error"]
    create = {"id": "atom-nuevo", "action": "create", "model": "KnowledgeAtom", "payload": atom_page["payload"]}
    assert api.post("/api/wiki/save", json={"changes": [create]}).status_code == 403
    delete = {"id": ATOM, "action": "delete", "model": "KnowledgeAtom", "expected": atom_page["payload"]}
    assert api.post("/api/wiki/save", json={"changes": [delete]}).status_code == 403
    assert atom_file.read_text(encoding="utf-8") == atom_text and _page(api, ATOM)["payload"] == atom_page["payload"]
    assert api.post("/api/wiki/models/promote", json={"model": "AgentDoc"}).status_code == 403

    # El encuadre del tutor sí: entra, queda escrito por sldb y lo usa el turno siguiente, sin reiniciar.
    new = "Eres un tutor de prueba que responde con una sola frase."
    saved = _update(api, agent_page, framing=new)
    assert saved.status_code == 200 and saved.json()["ok"] is True, saved.text
    assert _page(api, AGENT)["payload"]["framing"] == new
    written = (kbs / KB / agent_page["path"]).read_text(encoding="utf-8")
    assert new in written and "authority: authored" in written
    again = api.post("/api/chat", json={"message": "¿y dos?", "conversation_id": first["conversation_id"], "user_id": first["user_id"]}).json()
    assert new in again["turn"]["assistant_message"] and before not in again["turn"]["assistant_message"]  # la conversación ya abierta
    fresh = api.post("/api/chat", json={"message": "¿qué es uno?"}).json()
    assert new in fresh["turn"]["assistant_message"]  # y una nueva

    # Guardar sobre una versión que ya no es la vigente no pisa nada (lo detecta sldb).
    assert _update(api, agent_page, framing="otra cosa").status_code == 409

    # Un cambio que deja al tutor sin su página se deshace y lo dice.
    current = _page(api, AGENT)
    broken = _update(api, current, role="otro")
    assert broken.status_code == 422 and "se deshizo" in broken.json()["error"]
    assert _page(api, AGENT)["payload"] == current["payload"]
    assert new in api.post("/api/chat", json={"message": "¿sigues ahí?"}).json()["turn"]["assistant_message"]


# -- kb_build -------------------------------------------------------------------------------

BRANCH_MD = """---
id: branch-mini
title: Mini
tags:
- layer:taxonomy
- node:branch
- system:apos
node_type: branch
---

# Mini

## Descripción

Raíz de una base mínima de prueba.
"""

ATOM_MD = """---
id: {id}
title: {title}
five_wh_one_plus: what
tags:
- system:apos
- topic:prueba
node_type: knowledge
parent_id: branch-mini
---

# {title}

## Respuesta

{title} es un átomo de prueba.

## Procedencia

Nota de prueba.
"""


def test_kb_build_siembra_el_rol_una_vez_y_despues_conserva_lo_editado(tmp_path: Path) -> None:
    from sldb.api import save_document_payload

    atoms, out, pack = tmp_path / "atoms", tmp_path / "kbs" / "mini", tmp_path / "pack"
    (atoms / "branches").mkdir(parents=True)
    pack.mkdir()
    (atoms / "tag-namespaces.yaml").write_text((world.repo_root() / "desk" / "atoms" / "tag-namespaces.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (atoms / "branches" / "branch-mini.md").write_text(BRANCH_MD, encoding="utf-8")
    (atoms / "atom-a.md").write_text(ATOM_MD.format(id="atom-a", title="A"), encoding="utf-8")
    (pack / "persona.md").write_text("Persona del pack.", encoding="utf-8")
    (pack / "prompt_policy.md").write_text("Política del pack.", encoding="utf-8")

    def build():
        report = kb_build.build(atoms, out, pack_dir=pack, embedder_name="hash", index=False, anchor=False)
        assert report.is_valid, [e.line() for e in report.errors]
        return world.open_kb(out, build_if_missing=False)

    seeded = world.agent(build(), "tutor")
    assert seeded["framing"] == "Persona del pack." and seeded["instructions"] == "Política del pack."
    page = out / "agent" / f"{kb_build.AGENT_NAME}.md"
    assert "authority: authored" in page.read_text(encoding="utf-8")
    atom_page = out / "knowledge" / "atom-a.md"
    assert "authority: generated" in atom_page.read_text(encoding="utf-8")

    # Una persona cambia el encuadre (por sldb, como hace la wiki); el pack también cambia después.
    edited = {k: v for k, v in seeded.items() if k != "id"} | {"id": kb_build.AGENT_NAME, "framing": "Encuadre escrito en la wiki."}
    save_document_payload(out / ".sldb", "AgentDoc", kb_build.AGENT_NAME, edited, pythonpath=authoring.KbWriter(out).pythonpath, actor="prueba")
    (pack / "persona.md").write_text("Persona nueva del pack.", encoding="utf-8")
    (atoms / "atom-b.md").write_text(ATOM_MD.format(id="atom-b", title="B"), encoding="utf-8")
    text = page.read_text(encoding="utf-8")

    rebuilt = build()
    kept = world.agent(rebuilt, "tutor")
    assert kept["framing"] == "Encuadre escrito en la wiki." and kept["instructions"] == "Política del pack."
    assert page.read_text(encoding="utf-8") == text  # ni un byte: no se reescribe
    assert {a["id"] for a in world.list_atoms(rebuilt)} == {"atom-a", "atom-b"}  # lo generado sí se regenera

    # Sin la página (alguien borró `agent/`), se vuelve a sembrar desde el pack.
    page.unlink()
    assert world.agent(build(), "tutor")["framing"] == "Persona nueva del pack."
