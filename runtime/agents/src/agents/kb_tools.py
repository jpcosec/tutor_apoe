"""Tools de lectura de la KB para un agente (spec 05 §6.4, tabla de tools de KB; equivalen a las de pron).

Cada agente lee solo su porción de la KB: su `ProjectionDoc`. Lo que muestra `kb.show` queda en
`reads`; el turno lo suma al contexto del rol y lo vuelve citable (06 E2).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agents.providers import body_of
from kb import Document, KnowledgeBase

KB_TOOLS = ("kb.explore_multi", "kb.explore", "kb.show")
OUTSIDE = "fuera de tu porción de la KB"


class KbReader:
    def __init__(self, kb: KnowledgeBase, projection: str, allowed: list[str]) -> None:
        self.kb, self.allowed = kb, allowed
        self.visible: dict[str, Document] = {d.key: d for d in kb.in_projection(projection)}
        self.reads: list[str] = []

    def functions(self) -> list[Callable[..., str]]:
        """Las tools declaradas para el agente, con el nombre que ve el modelo (`kb_…`)."""
        table: dict[str, Callable[..., str]] = {
            "kb.explore_multi": self.kb_explore_multi,
            "kb.explore": self.kb_explore,
            "kb.show": self.kb_show,
        }
        return [table[name] for name in self.allowed]

    def kb_explore_multi(self, query: str, max_results: int = 10) -> str:
        """Busca en tu porción de la KB los documentos más parecidos a `query`.

        Devuelve una línea por documento: `Modelo:nombre · título · puntaje`. Para leer uno, usa kb_show.
        """
        hits = self.kb.rank(query, k=max_results, among=list(self.visible))
        return "\n".join(f"{h.ref} · {_title(h.document)} · {h.score:.2f}" for h in hits) or "sin resultados"

    def kb_explore(self, ref: str) -> str:
        """Los vecinos de un documento de tu porción (`Modelo:nombre`).

        Devuelve una línea por vecino: `Modelo:nombre · relación · título`.
        """
        if ref not in self.visible:
            return OUTSIDE
        lines = [
            f"{other} · {relation.relation_type} · {_title(self.visible[other])}"
            for relation, other in _neighbors(self.kb, ref)
            if other in self.visible
        ]
        return "\n".join(lines) or "sin vecinos en tu porción"

    def kb_show(self, ref: str) -> str:
        """El contenido de un documento de tu porción de la KB (`Modelo:nombre`).

        Lo que leas con esta tool lo puedes citar.
        """
        key = ref.strip().strip("[]`").removeprefix("kb:")
        if key not in self.visible:
            return OUTSIDE
        if key not in self.reads:
            self.reads.append(key)
        return f"[{key}]\n{body_of(self.kb, self.visible[key])}"


def _neighbors(kb: KnowledgeBase, ref: str) -> list[tuple[Any, str]]:
    return [(r, r.target_ref) for r in kb.outgoing(ref)] + [(r, r.source_ref) for r in kb.incoming(ref)]


def _title(document: Document) -> str:
    return str(document.payload.get("title") or document.name)
