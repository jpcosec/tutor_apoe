"""Ramas sin relleno: cobertura derivada de sus descendientes y descripciones reales.

- `compute_coverage(kb, outline)`: para cada `BranchNode`, la unión de la procedencia de todos sus
  átomos descendientes (capítulos, secciones, páginas, fragmentos anclados, conteos). Se recalcula en
  cada build y la `## Procedencia` de la rama se renderiza desde ahí.
- `describe_branches(kb, ids, model)`: UNA VEZ, con un LLM (`google-gla:gemini-2.5-flash`), 2–3
  oraciones en español sobre qué abarca la rama y cómo se relaciona con sus hermanas, a partir de los
  títulos y respuestas de sus hijos. Se escriben en la fuente de verdad `desk/atoms/branches/<id>.md`;
  `kb_build` las lee de ahí y no inventa texto.

    tutor compile branches --all            # regenera todas las descripciones en desk/atoms/branches
    tutor compile branches branch-apos-mechanisms --model google-gla:gemini-2.5-flash
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from kb_models.apos import provenance_items
from kb_models.provenance import Coverage, ProvenanceKind, section_key
from tutor import outline as outline_mod
from tutor import world

log = logging.getLogger(__name__)

DEFAULT_MODEL = "google-gla:gemini-2.5-flash"
BRANCH_TAGS = ["system:apos", "node:branch", "layer:taxonomy"]
BANNED = ("nodo de organización", "kb_build", "script", "parent_id", "esta rama", "este nodo", "esta categoría")
MAX_CHILD_ANSWER = 240
MAX_CHILDREN = 24
INSTRUCTIONS = """\
Eres el editor de una base de conocimiento sobre la teoría APOS (Arnon et al., 2014), organizada \
como un árbol de ramas con átomos de conocimiento en las hojas. Escribes la descripción de UNA rama \
para un estudiante que la ve en un visor: 2 o 3 oraciones en español, en prosa, que digan qué \
abarca la rama (los conceptos concretos que contienen sus hijos) y cómo se relaciona con sus ramas \
hermanas (qué la distingue de ellas o qué la une). Usa los términos del contenido (encapsulación, \
descomposición genética, ciclo ACE…), no metalenguaje: nunca hables de nodos, scripts, ids, \
archivos, taxonomías, bases de datos, y no uses las palabras «rama», «nodo», «categoría», «sección» \
ni «grupo» para referirte a ella o a sus hermanas: habla del tema directamente («La encapsulación es…», \
«Los dominios matemáticos en que APOS se ha aplicado…»). Sin encabezados, sin listas, sin comillas de \
apertura; devuelve solo el texto."""


# -- cobertura ------------------------------------------------------------------------------------


def _children_map(kb: Any) -> dict[str, list[str]]:
    kids: dict[str, list[str]] = {}
    for relation in kb.relations(world.RELATION):
        kids.setdefault(world._name(relation.target_ref), []).append(world._name(relation.source_ref))
    return kids


def descendants(kb: Any, branch_id: str, kids: dict[str, list[str]] | None = None) -> list[Any]:
    """Todos los documentos bajo la rama (átomos y ramas), en profundidad."""
    kids = kids if kids is not None else _children_map(kb)
    out: list[Any] = []
    stack = list(kids.get(branch_id, []))
    seen: set[str] = set()
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        try:
            document = kb.get(name)
        except KeyError:
            continue
        out.append(document)
        stack.extend(kids.get(name, []))
    return out


def coverage_of(atoms: list[Any], outline: dict[str, Any] | None = None) -> Coverage:
    """La `Coverage` de un conjunto de documentos de conocimiento."""
    sources: list[str] = []
    chapters: set[int] = set()
    sections: set[str] = set()
    pages: list[int] = []
    chunk_ids: list[str] = []
    n_expert = n_unanchored = 0
    for document in atoms:
        items = provenance_items(document.payload)
        book = [i for i in items if i.kind == ProvenanceKind.BOOK]
        if any(i.kind == ProvenanceKind.EXPERT for i in items):
            n_expert += 1
        if book and all(i.anchored is False for i in book):
            n_unanchored += 1
        for item in book:
            if item.source and item.source not in sources:
                sources.append(item.source)
            if item.chapter is not None:
                chapters.add(item.chapter)
            sections.update(item.numeric_sections)
            chunk_ids.extend(c for c in item.chunk_ids if c not in chunk_ids)
            if item.pages:
                pages.extend(item.pages)
            elif outline is not None:
                for number in item.numeric_sections or ([str(item.chapter)] if item.chapter is not None else []) + item.named_parts:
                    entry = outline_mod.entry_for(outline, number)
                    if entry and entry.get("page_start") and entry.get("page_end"):
                        pages.extend([int(entry["page_start"]), int(entry["page_end"])])
    return Coverage(
        sources=sources,
        chapters=sorted(chapters),
        sections=sorted(sections, key=section_key),
        pages=[min(pages), max(pages)] if pages else None,
        chunk_ids=chunk_ids,
        n_atoms=len(atoms),
        n_expert=n_expert,
        n_unanchored=n_unanchored,
    )


def compute_coverage(kb: Any, outline: dict[str, Any] | None = None) -> dict[str, Coverage]:
    """`{branch_id: Coverage}` para todas las ramas, a partir de sus átomos descendientes."""
    kids = _children_map(kb)
    out: dict[str, Coverage] = {}
    for branch in kb.by_model(world.BRANCH_MODEL):
        atoms = [d for d in descendants(kb, branch.name, kids) if d.is_a(world.KNOWLEDGE_MODEL)]
        out[branch.name] = coverage_of(atoms, outline)
    return out


def apply_coverage(writer: Any, outline: dict[str, Any] | None = None, *, refresh: bool = True) -> int:
    """Recalcula y escribe la `coverage` de todas las ramas; devuelve cuántas cambiaron."""
    from tutor import kb_build

    kb = writer.kb()
    coverage = compute_coverage(kb, outline)
    docs = []
    for branch in kb.by_model(world.BRANCH_MODEL):
        payload = dict(branch.payload)
        new = coverage[branch.name].model_dump(mode="json")
        current = payload.get("coverage")
        if current is not None and Coverage.model_validate(current).model_dump(mode="json") == new:  # sldb omite los None al leer
            continue
        docs.append(kb_build.Doc(branch.model, branch.path, {**payload, "coverage": new}, name=branch.name))
    if docs:
        writer.write_many(docs)
        if refresh:
            writer.refresh(index=False)
    return len(docs)


# -- descripciones ---------------------------------------------------------------------------------


def branch_context(kb: Any, branch_id: str) -> dict[str, Any]:
    """Lo que el modelo ve de una rama: título, padre, hermanas e hijos (ramas con su descripción,
    átomos con título y respuesta recortada)."""
    branch = world.get_atom(kb, branch_id) or {}
    parent = world.parent(kb, branch_id)
    siblings = [c["title"] for c in world.children(kb, parent["id"]) if c["id"] != branch_id and c["model"] == world.BRANCH_MODEL] if parent else []
    children = []
    for child in world.children(kb, branch_id)[:MAX_CHILDREN]:
        if child["model"] == world.BRANCH_MODEL:
            children.append({"kind": "rama", "title": child["title"], "text": str(child.get("summary") or "")[:MAX_CHILD_ANSWER]})
        else:
            children.append({"kind": "átomo", "title": child["title"], "text": str(child.get("summary") or "")[:MAX_CHILD_ANSWER]})
    if not children:  # rama intermedia sin hijos directos de conocimiento: sus descendientes
        for document in descendants(kb, branch_id)[:MAX_CHILDREN]:
            if document.is_a(world.KNOWLEDGE_MODEL):
                children.append({"kind": "átomo", "title": str(document.payload.get("title")), "text": str(document.payload.get("answer") or "")[:MAX_CHILD_ANSWER]})
    return {"id": branch_id, "title": branch.get("title") or branch_id, "parent": parent["title"] if parent else None, "siblings": siblings, "children": children}


def render_prompt(context: dict[str, Any]) -> str:
    lines = [f"Rama: {context['title']}"]
    if context["parent"]:
        lines.append(f"Rama madre: {context['parent']}")
    if context["siblings"]:
        lines.append("Ramas hermanas: " + "; ".join(context["siblings"]))
    lines.append("Contenido (hijos):")
    for child in context["children"]:
        lines.append(f"- [{child['kind']}] {child['title']}" + (f": {child['text']}" if child["text"] else ""))
    lines.append("\nEscribe la descripción de la rama.")
    return "\n".join(lines)


def clean_description(text: str) -> str:
    text = " ".join(str(text or "").split()).strip().strip('"«»')
    return text


def describe_branches(kb: Any, ids: list[str], *, model: str = DEFAULT_MODEL, agent_model: Any | None = None) -> dict[str, str]:
    """`{branch_id: descripción}` generada por el modelo (una llamada por rama)."""
    from pydantic_ai import Agent

    from tutor.agent import max_output_tokens, resolve_model

    resolved = agent_model if agent_model is not None else resolve_model(model)
    agent = Agent(resolved, output_type=str, instructions=INSTRUCTIONS)
    out: dict[str, str] = {}
    for branch_id in ids:
        context = branch_context(kb, branch_id)
        result = agent.run_sync(render_prompt(context), model_settings={"max_tokens": max_output_tokens()})
        text = clean_description(str(result.output))
        if not text:
            raise RuntimeError(f"{branch_id}: el modelo devolvió una descripción vacía")
        lowered = text.lower()
        if any(b in lowered for b in BANNED):
            log.warning("%s: la descripción usa metalenguaje (%s)", branch_id, text[:80])
        out[branch_id] = text
        log.info("%s: %s", branch_id, text[:100])
    return out


# -- escribir en desk/atoms/branches --------------------------------------------------------------


def desk_branch_file(desk_branches: Path, branch_id: str) -> Path:
    """El archivo existente de la rama (`atom-<id>.md` o `<id>.md`) o, si no hay, `<id>.md`."""
    for candidate in (desk_branches / f"{branch_id}.md", desk_branches / f"atom-{branch_id}.md"):
        if candidate.is_file():
            return candidate
    for path in desk_branches.glob("*.md"):
        if f"\nid: {branch_id}\n" in path.read_text(encoding="utf-8"):
            return path
    return desk_branches / f"{branch_id}.md"


def write_desk_branch(desk_branches: Path, branch: dict[str, Any], description: str, *, model: str, when: date | None = None) -> Path:
    """Escribe/reescribe `desk/atoms/branches/<id>.md` con la descripción real (sin sección de procedencia:
    la cobertura se deriva en el build)."""
    path = desk_branch_file(desk_branches, branch["id"])
    front = {
        "id": branch["id"],
        "title": branch["title"],
        "tags": list(branch.get("tags") or BRANCH_TAGS),
        "node_type": "branch",
        "parent_id": branch.get("parent") or None,
        "description_by": model,
        "description_at": (when or date.today()).isoformat(),
    }
    if front["parent_id"] is None:
        front.pop("parent_id")
    text = "---\n" + yaml.safe_dump(front, sort_keys=False, allow_unicode=True) + "---\n\n" + f"# {branch['title']}\n\n## Descripción\n\n{description}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def regenerate(kb: Any, ids: list[str], desk_branches: Path, *, model: str = DEFAULT_MODEL, agent_model: Any | None = None) -> dict[str, Path]:
    """Describe y escribe en desk las ramas pedidas; devuelve `{id: archivo}`."""
    descriptions = describe_branches(kb, ids, model=model, agent_model=agent_model)
    written: dict[str, Path] = {}
    for branch_id, text in descriptions.items():
        branch = world.get_atom(kb, branch_id) or {"id": branch_id, "title": branch_id}
        written[branch_id] = write_desk_branch(desk_branches, branch, text, model=model)
    return written


__all__ = [
    "BRANCH_TAGS",
    "DEFAULT_MODEL",
    "apply_coverage",
    "branch_context",
    "compute_coverage",
    "coverage_of",
    "descendants",
    "describe_branches",
    "regenerate",
    "render_prompt",
    "write_desk_branch",
]
