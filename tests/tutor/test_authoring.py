"""`tutor.authoring` e `tutor.ingest`: una KB creada desde cero valida con `kb`; los átomos se crean,
actualizan, enlazan y borran dejando la KB válida; un error inducido se detecta; la ingesta guarda
fragmentos fuera del índice y de la proyección del tutor. Todo en tmpdir, sin red."""

from __future__ import annotations

from pathlib import Path

import pytest
from kb import KnowledgeBase

from tutor import authoring, ingest, kb_build, world
from tutor.authoring import AuthoringError, KbWriter
from tutor.embedding import HashEmbedder

KB = "demo"
ROOT_BRANCH = f"branch-{KB}"


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("kbs")
    authoring.create_kb(KB, "Demo de prueba", description="KB de pruebas", root=base)
    return base


def _atom(title: str, parent: str = ROOT_BRANCH, **extra) -> dict:
    return {"title": title, "question": "what", "answer": f"Respuesta sobre {title}.", "provenance": "test", "tags": ["topic:prueba", f"system:{KB}"], "parent": parent, **extra}


# -- create_kb ------------------------------------------------------------------------------


def test_create_kb_is_valid_for_kb(root: Path) -> None:
    kb = KnowledgeBase.open(root / KB, HashEmbedder())  # lanza si no valida
    assert kb.validate().is_valid
    assert {d.name for d in kb.by_model("BranchNode")} == {ROOT_BRANCH}
    assert world.agent(kb, "tutor")["id"] == f"agent-tutor-{KB}"
    assert set(world.role_projection(kb, "tutor").models) == {"KnowledgeAtom", "BranchNode"}
    assert {d.payload["name"] for d in kb.by_model("RelationTypeDoc")} >= {"child_of"}
    assert (root / KB / "kb.yaml").is_file() and (root / KB / "tag-namespaces.yaml").is_file()
    assert "SourceDoc" in KbWriter(root / KB).registered_models()


def test_create_kb_rejects_duplicates_and_bad_ids(root: Path) -> None:
    with pytest.raises(AuthoringError, match="ya existe"):
        authoring.create_kb(KB, "otra", root=root)
    with pytest.raises(AuthoringError, match="kb_id inválido"):
        authoring.create_kb("Mala_KB", "x", root=root)


def test_list_kbs(root: Path) -> None:
    listed = authoring.list_kbs(root)
    assert [k["kb_id"] for k in listed] == [KB]
    assert listed[0]["roles"] == ["tutor"] and listed[0]["valid"] is True
    assert {"kb_id", "path", "n_atoms", "n_branches", "roles"} <= set(listed[0])


def test_slugify() -> None:
    assert authoring.slugify("La Acción, en APOS!", "atom-") == "atom-la-accion-en-apos"
    assert authoring.slugify("atom-ya-con-prefijo", "atom-") == "atom-ya-con-prefijo"
    with pytest.raises(AuthoringError):
        authoring.slugify("¡¡¡", "atom-")


# -- átomos y ramas -------------------------------------------------------------------------


def test_upsert_update_delete_atom(root: Path) -> None:
    branch = authoring.upsert_branch(KB, {"title": "Conceptos", "parent": ROOT_BRANCH, "summary": "Los conceptos"}, root=root)
    assert branch["id"] == "branch-conceptos" and branch["created"] is True
    created = authoring.upsert_atom(KB, _atom("La acción es externa", parent="branch-conceptos"), root=root)
    assert created["id"] == "atom-la-accion-es-externa" and created["created"] is True
    assert created["parent"] == "branch-conceptos" and created["model"] == "KnowledgeAtom"
    assert (root / KB / "knowledge" / "atom-la-accion-es-externa.md").is_file()
    assert (root / KB / "relations" / "child_of--atom-la-accion-es-externa--branch-conceptos.md").is_file()

    kb = KnowledgeBase.open(root / KB, HashEmbedder())
    assert [c["id"] for c in world.children(kb, "branch-conceptos")] == ["atom-la-accion-es-externa"]
    assert world.rank(kb, "acción externa", 1)[0][0] == "atom-la-accion-es-externa"

    updated = authoring.upsert_atom(KB, {**_atom("La acción es externa"), "id": created["id"], "answer": "Nueva respuesta.", "question": "how"}, root=root)
    assert updated["created"] is False and updated["summary"] == "Nueva respuesta." and updated["question"] == "how"
    assert updated["parent"] == ROOT_BRANCH
    writer = KbWriter(root / KB)
    assert [d.name for d in writer.relations_of(created["id"], "child_of")] == [f"child_of--{created['id']}--{ROOT_BRANCH}"]
    assert authoring.validate_kb(KB, root)["ok"]

    deleted = authoring.delete_atom(KB, created["id"], root=root)
    assert deleted["deleted"] == created["id"] and deleted["relations_removed"]
    assert not (root / KB / "knowledge" / "atom-la-accion-es-externa.md").exists()
    assert authoring.validate_kb(KB, root)["ok"]
    assert world.get_atom(KnowledgeBase.open(root / KB, HashEmbedder()), created["id"]) is None


def test_upsert_atom_requires_existing_parent_and_valid_fields(root: Path) -> None:
    with pytest.raises(AuthoringError, match="no existe el parent"):
        authoring.upsert_atom(KB, _atom("Huérfano", parent="branch-no-existe"), root=root)
    with pytest.raises(AuthoringError, match="question inválida"):
        authoring.upsert_atom(KB, {**_atom("x"), "question": "quien"}, root=root)
    with pytest.raises(AuthoringError, match="inválido"):
        authoring.upsert_atom(KB, {**_atom("x"), "tags": ["SinNamespace"]}, root=root)
    with pytest.raises(AuthoringError, match="answer"):
        authoring.upsert_atom(KB, {**_atom("x"), "answer": ""}, root=root)


def test_new_tag_namespace_is_declared(root: Path) -> None:
    atom = authoring.upsert_atom(KB, _atom("Con namespace nuevo", tags=["nivel:basico"]), root=root)
    assert atom["declared_namespaces"] == ["nivel"]
    assert (root / KB / "categories" / "category-nivel.md").is_file()
    assert "nivel" in (root / KB / "tag-namespaces.yaml").read_text(encoding="utf-8")
    assert authoring.validate_kb(KB, root)["ok"]


def test_link_atoms_declares_type_and_validates(root: Path) -> None:
    a = authoring.upsert_atom(KB, _atom("Origen del enlace"), root=root)
    b = authoring.upsert_atom(KB, _atom("Destino del enlace"), root=root)
    link = authoring.link_atoms(KB, a["id"], "requires", b["id"], description="A presupone B.", root=root)
    assert link["type_declared"] is True and link["relation"] == f"requires--{a['id']}--{b['id']}"
    assert (root / KB / "kgdb" / "relation_types" / "requires.md").is_file()
    again = authoring.link_atoms(KB, b["id"], "requires", a["id"], root=root)
    assert again["type_declared"] is False
    kb = KnowledgeBase.open(root / KB, HashEmbedder())
    assert kb.stats().relations_by_type["requires"] == 2
    with pytest.raises(AuthoringError, match="no existe"):
        authoring.link_atoms(KB, a["id"], "requires", "atom-nope", root=root)
    # child_of vía link_atoms mueve el átomo de rama
    authoring.link_atoms(KB, a["id"], "child_of", "branch-conceptos", root=root)
    assert world.parent(KnowledgeBase.open(root / KB, HashEmbedder()), a["id"])["id"] == "branch-conceptos"
    assert authoring.validate_kb(KB, root)["ok"]


def test_branch_rules(root: Path) -> None:
    with pytest.raises(AuthoringError, match="debe ser una rama"):
        atom = authoring.upsert_atom(KB, _atom("Soy átomo"), root=root)
        authoring.upsert_branch(KB, {"title": "Hija de átomo", "parent": atom["id"]}, root=root)
    sub = authoring.upsert_branch(KB, {"title": "Subrama", "parent": "branch-conceptos"}, root=root)
    with pytest.raises(AuthoringError, match="ciclo"):
        authoring.upsert_branch(KB, {"id": "branch-conceptos", "title": "Conceptos", "parent": sub["id"]}, root=root)
    with pytest.raises(AuthoringError, match="tiene .* hijos"):
        authoring.delete_atom(KB, "branch-conceptos", root=root)


def test_upsert_agent(root: Path) -> None:
    agent = authoring.upsert_agent(KB, "evaluador", "Eres un evaluador.", "Califica con rúbrica.", "Evaluador demo", root=root)
    assert agent["id"] == f"agent-evaluador-{KB}" and agent["framing"] == "Eres un evaluador."
    kb = KnowledgeBase.open(root / KB, HashEmbedder())
    assert world.role_projection(kb, "evaluador").relations == ["child_of"]
    assert {t["role"] for t in authoring.list_tutors(KB, root)} == {"tutor", "evaluador"}


# -- validate / rebuild -------------------------------------------------------------------------


def test_validate_detects_induced_error(tmp_path: Path) -> None:
    authoring.create_kb("broken", "Rota", root=tmp_path)
    atom = authoring.upsert_atom("broken", {**_atom("Átomo bien"), "parent": "branch-broken", "tags": ["system:broken"]}, root=tmp_path)
    writer = KbWriter(tmp_path / "broken")
    # una relación child_of hacia una rama que no existe, escrita por debajo de las validaciones de upsert
    writer.write(kb_build.relation_doc("KnowledgeAtom", atom["id"], "BranchNode", "branch-fantasma"))
    writer.refresh(index=False)
    report = authoring.validate_kb("broken", tmp_path)
    assert report["ok"] is False
    assert report["errors"], report
    assert any("branch-fantasma" in e["message"] for e in report["errors"]), report["errors"]
    writer.delete(f"child_of--{atom['id']}--branch-fantasma")
    writer.refresh(index=False)
    assert authoring.validate_kb("broken", tmp_path)["ok"]


def test_validate_missing_kb(root: Path) -> None:
    with pytest.raises(AuthoringError, match="no existe la KB"):
        authoring.validate_kb("nada", root)


def test_rebuild_kb_from_markdown(root: Path) -> None:
    before = authoring.validate_kb(KB, root)["stats"]
    result = authoring.rebuild_kb(KB, root)
    assert result["ok"] is True and result["skipped"] == []
    assert result["stats"]["by_model"] == before["by_model"]
    assert result["tracked"]["KnowledgeAtom"] == before["by_model"]["KnowledgeAtom"]


# -- ingest -------------------------------------------------------------------------------------


def test_chunk_text_offsets() -> None:
    text = "Primer párrafo. " * 20 + "\n\n" + "Segundo párrafo corto.\n\n" + "Tercero. " * 100
    chunks = ingest.chunk_text(text, chunk_chars=400)
    assert len(chunks) >= 3
    for chunk in chunks:
        assert len(chunk["text"]) <= 400
        assert text[chunk["start"] : chunk["end"]].strip() == chunk["text"]
    assert [c["index"] for c in chunks] == list(range(len(chunks)))
    with pytest.raises(AuthoringError):
        ingest.chunk_text(text, chunk_chars=10)


def test_ingest_text_excluded_from_index_and_projection(root: Path) -> None:
    text = "La encapsulación convierte un proceso en objeto.\n\n## Sección\n\n" + "Un objeto admite nuevas acciones. " * 40
    result = ingest.ingest_text(KB, "Fuente uno", text, chunk_chars=500, root=root)
    assert result["source_id"] == "source-fuente-uno" and result["n_chunks"] >= 2
    chunk = result["chunks"][0]
    assert chunk["chunk_id"] == "source-fuente-uno-chunk-0" and chunk["start"] == 0
    assert (root / KB / "ingest" / "sources" / "source-fuente-uno.md").is_file()
    assert (root / KB / "ingest" / "chunks" / "source-fuente-uno" / "source-fuente-uno-chunk-0.md").is_file()

    kb = KnowledgeBase.open(root / KB, HashEmbedder())
    assert kb.validate().is_valid
    visible = {d.model for d in kb.in_projection("tutor")}
    assert visible <= {"KnowledgeAtom", "BranchNode"}
    assert len(kb.by_model("SourceChunk")) == result["n_chunks"]
    ranked = {name for name, _ in world.rank(kb, "la encapsulación convierte un proceso en objeto", 20)}
    assert not any(name.startswith("source-") for name in ranked)
    assert all(hit.model == "KnowledgeAtom" for hit in kb.rank("objeto admite nuevas acciones", 20))

    got = ingest.get_chunk(KB, chunk["chunk_id"], root=root)
    assert got["source"] == "source-fuente-uno" and got["index"] == 0
    assert got["text"].startswith("La encapsulación convierte un proceso en objeto.")
    assert "**Sección**" in got["text"] and "## Sección" not in got["text"]  # sin encabezados dentro del campo
    assert ingest.list_sources(KB, root)[0]["n_chunks"] == result["n_chunks"]

    replaced = ingest.ingest_text(KB, "Fuente uno", "Texto nuevo y corto.", root=root)
    assert replaced["replaced"] is True and replaced["n_chunks"] == 1
    assert len(KnowledgeBase.open(root / KB, HashEmbedder()).by_model("SourceChunk")) == 1
    removed = ingest.delete_source(KB, "source-fuente-uno", root=root)
    assert removed["chunks_removed"] == 1
    assert authoring.validate_kb(KB, root)["ok"]


def test_ingest_file_txt_and_md(root: Path, tmp_path: Path) -> None:
    source = tmp_path / "notas_de_clase.md"
    source.write_text("# Título\n\nUn párrafo.\n\nOtro párrafo.", encoding="utf-8")
    result = ingest.ingest_file(KB, source, root=root)
    assert result["source_id"] == "source-notas-de-clase" and result["path"] == str(source)
    assert result["chunks"][0]["text"].startswith("# Título")
    with pytest.raises(AuthoringError, match="no existe el archivo"):
        ingest.ingest_file(KB, tmp_path / "nada.txt", root=root)
    with pytest.raises(AuthoringError, match="formato no soportado"):
        (tmp_path / "x.docx").write_bytes(b"")
        ingest.ingest_file(KB, tmp_path / "x.docx", root=root)


def test_ingest_pdf_if_pypdf(root: Path, tmp_path: Path) -> None:
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    target = tmp_path / "vacio.pdf"
    with target.open("wb") as handle:
        writer.write(handle)
    assert ingest.read_pdf(target) == ""
    with pytest.raises(AuthoringError, match="vacío"):
        ingest.ingest_file(KB, target, root=root)
