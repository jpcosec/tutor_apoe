"""La superficie de texto: el PDF por páginas con los átomos anclados a cada tramo, en los dos sentidos.

Es la «vista uno» de la visión de tres superficies (texto / átomos / grafo): a la izquierda el texto de
la fuente, a la derecha los átomos que se verifican en lo visible; pasar por un átomo resalta sus
tramos y pasar por un tramo resalta sus átomos. Este módulo prepara los datos; `tutor.web` los sirve
en `/api/surface/*` y `static/surface/` los dibuja.

    from tutor import surface
    view = surface.SurfaceView(kb)
    view.outline()                 # esquema + mapa de cobertura por página
    view.page(32)                  # fragmentos de la página 32 con sus átomos anclados
    view.atom("atom-…")            # el átomo con sus anclas (fragmento, página, cita)
"""

from __future__ import annotations

from typing import Any

from kb_models.provenance import ProvenanceKind

from tutor import outline as outline_mod
from tutor import world


class SurfaceView:
    """Índices derivados de una KB abierta: página → fragmentos, fragmento → átomos, átomo → anclas."""

    def __init__(self, kb: Any, source_id: str | None = None) -> None:
        self.kb = kb
        sources = kb.by_model("SourceDoc")
        self.source_id = source_id or (sources[0].name if sources else None)
        self.source_title = next((str(d.payload.get("title") or d.name) for d in sources if d.name == self.source_id), self.source_id or "")
        self.chunks: dict[str, dict[str, Any]] = {}
        self.by_page: dict[int, list[str]] = {}
        for document in sorted(kb.by_model("SourceChunk"), key=lambda d: int(d.payload.get("index") or 0)):
            if self.source_id and document.payload.get("source") != self.source_id:
                continue
            page = int(document.payload.get("page") or 0)
            row = {"chunk_id": document.name, "index": int(document.payload.get("index") or 0), "page": page, "text": str(document.payload.get("text") or "")}
            self.chunks[document.name] = row
            self.by_page.setdefault(page, []).append(document.name)
        self.pages = sorted(p for p in self.by_page if p)
        self.outline_doc = outline_mod.load_outline(kb, self.source_id) if self.source_id else None
        self.atoms: dict[str, dict[str, Any]] = {}
        self.atoms_by_chunk: dict[str, list[str]] = {}
        for document in kb.by_model(world.KNOWLEDGE_MODEL):
            flat = world.atom_dict(document)
            anchors = []
            for ref in flat["provenance_refs"]:
                for position, chunk_id in enumerate(ref.get("chunk_ids") or []):
                    if chunk_id not in self.chunks:
                        continue
                    anchors.append({
                        "chunk_id": chunk_id,
                        "page": self.chunks[chunk_id]["page"],
                        "noul": (ref.get("nouls") or [None] * (position + 1))[position] if position < len(ref.get("nouls") or []) else None,
                        "excerpt": ref.get("excerpt") if position == 0 else None,
                    })
                    self.atoms_by_chunk.setdefault(chunk_id, []).append(document.name)
            self.atoms[document.name] = {**flat, "anchors": anchors, "status": atom_status(flat["provenance_refs"])}

    # -- consultas ------------------------------------------------------------------------

    def outline(self) -> dict[str, Any]:
        """Esquema (capítulos/secciones con páginas) y mapa de cobertura: por página, cuántos fragmentos y átomos."""
        coverage = []
        for page in self.pages:
            ids = self.by_page[page]
            atoms = sorted({a for c in ids for a in self.atoms_by_chunk.get(c, [])})
            coverage.append({"page": page, "n_chunks": len(ids), "n_atoms": len(atoms)})
        entries = [e for e in (self.outline_doc or {}).get("entries") or [] if e.get("page_start")]
        return {
            "source": self.source_id,
            "title": self.source_title,
            "n_pages": max(self.pages) if self.pages else 0,
            "pages": coverage,
            "entries": entries,
            "n_atoms": len(self.atoms),
            "n_anchored": sum(1 for a in self.atoms.values() if a["anchors"]),
            "n_unanchored": sum(1 for a in self.atoms.values() if a["status"] == "unanchored"),
        }

    def section_of(self, page: int) -> dict[str, Any] | None:
        """La entrada más específica del esquema que contiene la página."""
        best = None
        for entry in (self.outline_doc or {}).get("entries") or []:
            start, end = entry.get("page_start"), entry.get("page_end")
            if start and end and start <= page <= end and (best is None or entry["level"] >= best["level"]):
                best = entry
        return best

    def page(self, number: int) -> dict[str, Any] | None:
        if number not in self.by_page:
            return None
        chunks = []
        atom_ids: list[str] = []
        for chunk_id in self.by_page[number]:
            row = self.chunks[chunk_id]
            ids = self.atoms_by_chunk.get(chunk_id, [])
            chunks.append({**row, "atoms": ids})
            atom_ids.extend(i for i in ids if i not in atom_ids)
        later = [p for p in self.pages if p > number]
        earlier = [p for p in self.pages if p < number]
        return {
            "page": number,
            "section": self.section_of(number),
            "chunks": chunks,
            "atoms": [self.atom_card(i) for i in atom_ids],
            "prev": earlier[-1] if earlier else None,
            "next": later[0] if later else None,
        }

    def atom_card(self, atom_id: str) -> dict[str, Any]:
        atom = self.atoms[atom_id]
        return {
            "id": atom_id,
            "title": atom["title"],
            "question": atom["question"],
            "tags": atom["tags"],
            "citation": atom["provenance"],
            "status": atom["status"],
            "anchors": atom["anchors"],
            "parent": atom["parent"],
        }

    def atom(self, atom_id: str) -> dict[str, Any] | None:
        atom = self.atoms.get(atom_id)
        if atom is None:
            return None
        first = atom["anchors"][0] if atom["anchors"] else None
        return {
            **self.atom_card(atom_id),
            "answer": atom["summary"],
            "citation_full": atom["citation"],
            "provenance_refs": atom["provenance_refs"],
            "surface_url": atom["surface_url"],
            "graph_url": f"/graph?highlight={atom_id}",
            "chat_url": f"/?atom={atom_id}",
            "first_page": first["page"] if first else None,
            "first_chunk": first["chunk_id"] if first else None,
        }

    def chunk(self, chunk_id: str) -> dict[str, Any] | None:
        row = self.chunks.get(chunk_id)
        if row is None:
            return None
        return {**row, "atoms": [self.atom_card(i) for i in self.atoms_by_chunk.get(chunk_id, [])]}


def atom_status(refs: list[dict[str, Any]]) -> str:
    """`anchored` | `unanchored` (buscó respaldo y no lo halló) | `expert` | `derived` | `pending` (sin evaluar)."""
    if not refs:
        return "derived"
    kinds = {r.get("kind") for r in refs}
    if any(r.get("chunk_ids") for r in refs):
        return "anchored"
    if ProvenanceKind.BOOK.value in kinds:
        return "unanchored" if any(r.get("anchored") is False for r in refs) else "pending"
    if ProvenanceKind.EXPERT.value in kinds:
        return "expert"
    return "derived"


__all__ = ["SurfaceView", "atom_status"]
