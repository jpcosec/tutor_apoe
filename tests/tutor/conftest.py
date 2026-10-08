"""Rutas para que `python -m pytest tests/tutor -q` corra sin PYTHONPATH: los paquetes
vendoreados en `runtime/*/src`, el esquema en `kbs/` y el código en `src/`."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PATHS = [
    REPO / "runtime" / "ontology" / "src",
    REPO / "runtime" / "cognitive" / "src",
    REPO / "runtime" / "kb" / "src",
    REPO / "runtime" / "embeddings" / "src",
    REPO / "runtime" / "llm" / "src",
    REPO / "runtime" / "agents" / "src",
    REPO / "runtime" / "tools" / "src",
    REPO / "runtime" / "semantics" / "src",
    REPO / "runtime" / "context" / "src",
    REPO / "kbs",
    REPO / "src",
]
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
for path in reversed(PATHS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture(scope="session")
def kb_root() -> Path:
    return REPO / "kbs" / "apos"


@pytest.fixture(scope="session")
def kb(kb_root: Path):
    from tutor.embedding import HashEmbedder
    from tutor.world import open_kb

    return open_kb(kb_root, HashEmbedder())
