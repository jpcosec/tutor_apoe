"""La superficie de texto sobre `kbs/apos`: esquema con mapa de cobertura, página con fragmentos y átomos
anclados en ambos sentidos, átomo con sus anclas y deep links; la mesa del chat y el grafo llevan la cita."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tutor.surface import SurfaceView, atom_status
from tutor.web import create_app

ATOM = "atom-encapsulation-treats-a-process-as-a-static-entity"


@pytest.fixture(scope="module")
def client(kb_root) -> TestClient:
    return TestClient(create_app(kb_root, model="test"))


def test_surface_page_and_static(client: TestClient) -> None:
    res = client.get("/surface")
    assert res.status_code == 200 and "<html" in res.text.lower() and "surface.js" in res.text
    assert client.get("/surface/static/surface.js").status_code == 200
    assert client.get("/surface/static/surface.css").status_code == 200


def test_outline_has_entries_and_coverage_map(client: TestClient) -> None:
    data = client.get("/api/surface/outline").json()
    assert data["source"] == "source-arnon-et-al-2014-apos-theory" and data["n_pages"] == 259
    assert data["n_atoms"] == 94 and data["n_anchored"] >= 60
    numbers = [e["number"] for e in data["entries"]]
    assert {"Prefacio", "Tabla de contenidos", "1", "3.2.3", "11", "Index"} <= set(numbers)
    assert all(e["page_start"] and e["page_end"] >= e["page_start"] for e in data["entries"])
    pages = {p["page"]: p for p in data["pages"]}
    assert len(pages) > 200 and any(p["n_atoms"] == 0 for p in pages.values()) and any(p["n_atoms"] > 0 for p in pages.values())


def test_page_links_chunks_and_atoms_both_ways(client: TestClient) -> None:
    atom = client.get(f"/api/surface/atom/{ATOM}").json()
    assert atom["status"] == "anchored" and atom["anchors"] and atom["first_page"] and atom["first_chunk"]
    assert atom["surface_url"] == f"/surface?atom={ATOM}" and atom["graph_url"] == f"/graph?highlight={ATOM}" and atom["chat_url"] == f"/?atom={ATOM}"
    assert atom["citation"].startswith("Arnon et al. (2014), cap. 3 §3.2.3, p") and atom["anchors"][0]["excerpt"]
    page = client.get(f"/api/surface/page/{atom['first_page']}").json()
    assert page["page"] == atom["first_page"] and page["section"]["number"].startswith("3.2")
    chunk = next(c for c in page["chunks"] if c["chunk_id"] == atom["first_chunk"])
    assert ATOM in chunk["atoms"] and chunk["text"]
    assert any(a["id"] == ATOM for a in page["atoms"])
    assert page["prev"] and page["next"]
    via_chunk = client.get(f"/api/surface/chunk/{atom['first_chunk']}").json()
    assert any(a["id"] == ATOM for a in via_chunk["atoms"]) and via_chunk["page"] == atom["first_page"]
    assert client.get("/api/surface/page/100000").status_code == 404
    assert client.get("/api/surface/atom/nope").status_code == 404
    assert client.get("/api/surface/chunk/nope").status_code == 404


def test_mesa_items_and_graph_carry_citation(client: TestClient) -> None:
    turn = client.post("/api/chat", json={"message": "¿qué es la encapsulación en APOS?"}).json()["turn"]
    items = turn["mesa"]["items"]
    assert items and all("citation" in i and "surface_url" in i for i in items)
    assert any(i["citation"].startswith("Arnon et al. (2014)") for i in items)
    nodes = {n["id"]: n for n in client.get("/api/graph").json()["atoms"]}
    node = nodes[ATOM]
    assert node["citation"].startswith("Arnon et al. (2014), cap. 3 §3.2.3") and node["surface_url"] == f"/surface?atom={ATOM}"
    assert node["provenance_refs"][0]["chunk_ids"]
    branch = nodes["branch-apos-mechanisms-encapsulation"]
    assert branch["provenance"].startswith("Cubre Arnon et al. (2014) cap. 3") and branch["coverage"]["n_atoms"] == 2
    assert client.get(f"/api/atom/{ATOM}").json()["surface_url"] == f"/surface?atom={ATOM}"


def test_atom_status() -> None:
    assert atom_status([]) == "derived"
    assert atom_status([{"kind": "book", "chunk_ids": ["c"]}]) == "anchored"
    assert atom_status([{"kind": "book", "chunk_ids": [], "anchored": False}]) == "unanchored"
    assert atom_status([{"kind": "book", "chunk_ids": [], "anchored": None}]) == "pending"
    assert atom_status([{"kind": "expert"}]) == "expert"


def test_surface_view_direct(kb) -> None:
    view = SurfaceView(kb)
    assert view.pages and view.section_of(32)["number"] == "3.2.3"
    assert view.page(1) is not None and view.page(10**6) is None
