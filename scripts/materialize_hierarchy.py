"""Convierte la taxonomía de carpetas de Tutor APOE en nodos SLDB explícitos.

Cada directorio que contiene conocimiento recibe un AtomDoc de tipo ``branch``
y cada átomo existente recibe ``parent_id`` + ``node_type``. Tras ejecutarlo,
la relación padre-hijo vive en los documentos, no en la ruta física.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ATOMS = ROOT / "desk" / "atoms"
BRANCHES = ATOMS / "branches"


def slug(parts: tuple[str, ...]) -> str:
    return re.sub(r"[^a-z0-9]+", "-", "-".join(parts).lower()).strip("-")


def branch_id(parts: tuple[str, ...]) -> str:
    return f"branch-{slug(parts)}"


def replace_or_add(meta: str, field: str, value: str) -> str:
    line = f"{field}: {value}"
    if re.search(rf"^{re.escape(field)}:", meta, flags=re.MULTILINE):
        return re.sub(rf"^{re.escape(field)}:.*$", line, meta, flags=re.MULTILINE)
    return meta.rstrip() + "\n" + line + "\n"


def split_doc(text: str) -> tuple[str, str]:
    _, meta, body = text.split("---\n", 2)
    return meta, body


def atom_paths() -> list[Path]:
    return [path for path in ATOMS.rglob("atom-*.md") if BRANCHES not in path.parents]


def main() -> None:
    paths = atom_paths()
    directories = sorted({path.parent.relative_to(ATOMS) for path in paths}, key=lambda item: (len(item.parts), item))
    for directory in directories:
        branch_path = BRANCHES / f"atom-{branch_id(directory.parts)}.md"
        parent = branch_id(directory.parts[:-1]) if len(directory.parts) > 1 else ""
        title = directory.name.replace("-", " ").replace("_", " ").title()
        branch_path.parent.mkdir(parents=True, exist_ok=True)
        if not branch_path.exists():
            branch_path.write_text(
                "\n".join((
                    "---", f"id: {branch_id(directory.parts)}", f"title: {title}",
                    "five_wh_one_plus: what", "tags:", "  - system:apos", "  - node:branch",
                    "  - layer:taxonomy", "node_type: branch", f"parent_id: {parent}", "---", "",
                    f"# {title}", "", "## Respuesta", "", "Nodo de organización de la base de conocimiento APOS.",
                    "", "## Procedencia", "", "Estructura taxonómica del repositorio.", "",
                )), encoding="utf-8")
    for path in paths:
        meta, body = split_doc(path.read_text(encoding="utf-8"))
        parent = branch_id(path.parent.relative_to(ATOMS).parts)
        meta = replace_or_add(meta, "node_type", "knowledge")
        meta = replace_or_add(meta, "parent_id", parent)
        path.write_text(f"---\n{meta}---\n{body}", encoding="utf-8")
    for branch_path in BRANCHES.glob("atom-*.md"):
        subprocess.run(
            ["sldb", "docs", "track", "--model", "AtomDoc", "--store", ".sldb", "--pythonpath", ".", "--force", str(branch_path.relative_to(ROOT))],
            cwd=ROOT, check=True, stdout=subprocess.DEVNULL,
        )
    subprocess.run(["sldb", "stores", "update", "--store", ".sldb", "--pythonpath", "."], cwd=ROOT, check=True)
    print(f"Materializadas {len(directories)} ramas y enlazados {len(paths)} átomos.")


if __name__ == "__main__":
    main()
