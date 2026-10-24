"""§3.0: el módulo habla con sldb solo por `sldb.api` y por excepciones deliberadas listadas aquí."""

from __future__ import annotations

import ast
from pathlib import Path

import kb

GATEWAY = "loading/sldb_gateway.py"
ALLOWED_EXCEPTIONS = {
    "sldb.runtime.validation",  # Validator (§6.1)
    "sldb.core.exceptions",  # contrato de errores
    "sldb.models.builtin_relation_types",  # los 11 tipos estructurales (§3.2)
}


def _sldb_imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "sldb":
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if alias.name.split(".")[0] == "sldb")
    return found


def test_solo_sldb_api_y_excepciones_declaradas() -> None:
    package = Path(kb.__file__).parent
    imports = {path.relative_to(package).as_posix(): _sldb_imports(path) for path in package.rglob("*.py")}

    outside_gateway = {p: mods - {"sldb"} for p, mods in imports.items() if p != GATEWAY and mods - {"sldb"}}
    public = {mod for mod in imports[GATEWAY] if mod == "sldb.api" or mod.startswith("sldb.api.")}
    unexpected = imports[GATEWAY] - {"sldb"} - public - ALLOWED_EXCEPTIONS

    assert outside_gateway == {}
    assert unexpected == set()
    assert not any("sldb.cli" in mod for mods in imports.values() for mod in mods)
