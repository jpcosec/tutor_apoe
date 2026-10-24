"""13 I1: el paquete solo importa la biblioteca estándar y Pydantic."""

import ast
import sys
from pathlib import Path

import pytest

import ontology

ALLOWED_THIRD_PARTY = {"pydantic"}


def _imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.spec("13-I1")
def test_solo_stdlib_y_pydantic() -> None:
    package_dir = Path(ontology.__file__).parent
    offending = {
        f"{path.name}: {root}"
        for path in package_dir.rglob("*.py")
        for root in _imported_roots(path)
        if root not in sys.stdlib_module_names and root not in ALLOWED_THIRD_PARTY and root != "ontology"
    }

    assert not offending
