"""Secciones fijas de las instrucciones, leídas de la KB por el tag que declara cada una (spec 16).

El módulo no conoce clases de modelo ni tags de ninguna KB: el agente declara qué tag lee cada
sección y con qué título (spec 01 §3.3, 05 I2).
"""

from __future__ import annotations

from agents.declaration import StaticSection
from kb import Document, KnowledgeBase, strip_frontmatter


def documents_with_tag(kb: KnowledgeBase, tag: str, projection: str = "all") -> list[Document]:
    """Los documentos con ese tag de modelo que la proyección del agente deja ver (14 §6.3)."""
    documents = [d for d in kb.eligible() if tag in d.model_tags]
    if projection == "all":
        return documents
    visible = {d.key for d in kb.in_projection(projection)}
    return [d for d in documents if d.key in visible]


def is_general(document: Document) -> bool:
    """Sin `applies_when`: va en las instrucciones fijas; con él, es una variante por segmento."""
    return not document.payload.get("applies_when")


def section_documents(
    kb: KnowledgeBase, section: StaticSection, role: str, projection: str
) -> list[Document]:
    """Lo que la sección lee de la KB. El encuadre se dirige por rol y no pasa por la proyección."""
    if section.render == "framing":
        return [d for d in documents_with_tag(kb, section.tag) if d.payload.get("role") == role]
    return documents_with_tag(kb, section.tag, projection)


def section(kb: KnowledgeBase, spec: StaticSection, role: str, projection: str = "all") -> str | None:
    """El texto de una sección, o None si la KB no declara nada para ella."""
    documents = section_documents(kb, spec, role, projection)
    if spec.render == "step_graph":
        body = _step_graph(kb, documents)
    elif spec.render == "cited":
        body = "\n\n".join(_cited(kb, d) for d in documents if is_general(d))
    else:
        general = documents if spec.render == "framing" else [d for d in documents if is_general(d)]
        body = "\n\n".join(body_of(kb, d) for d in general)
    return f"## {spec.title}\n\n{body}" if body else None


def _cited(kb: KnowledgeBase, document: Document) -> str:
    """El documento con su título y su ref, para que el agente pueda nombrarlo (p. ej. un criterio)."""
    title = document.payload.get("title") or document.name
    return f"### {title} [{document.key}]\n\n{body_of(kb, document)}"


def body_of(kb: KnowledgeBase, document: Document) -> str:
    """El render de sldb sin frontmatter ni título, con sus secciones un nivel más abajo y sin las vacías."""
    lines = strip_frontmatter(kb.render(document.key)).strip().split("\n")
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return "\n\n".join(_non_empty_sections(lines)).strip()


def _non_empty_sections(lines: list[str]) -> list[str]:
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in lines:
        if line.startswith("## "):
            sections.append(("#" + line, []))
        else:
            sections[-1][1].append(line)
    rendered: list[str] = []
    for heading, body in sections:
        text = "\n".join(body).strip()
        if text:
            rendered.append(f"{heading}\n\n{text}" if heading else text)
    return rendered


def _step_graph(kb: KnowledgeBase, steps: list[Document]) -> str:
    lines: list[str] = []
    for step in steps:
        targets = [r.target_ref.split(":")[-1] for r in kb.outgoing(step.key, "transitions_to")]
        title = step.payload.get("title") or step.name
        lines.append(f"- {step.name} ({title}) → {', '.join(targets) if targets else 'fin'}")
    return "\n".join(lines)
