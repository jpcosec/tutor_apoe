from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

from kb import KnowledgeBase
from make_fixture import KbSpec, build, minimal

WORKSPACE = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def minimal_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build(minimal(), tmp_path_factory.mktemp("kb-minima"))


@pytest.fixture(scope="session")
def minimal_kb(minimal_root: Path) -> KnowledgeBase:
    return KnowledgeBase.open(minimal_root)


@pytest.fixture
def build_kb(tmp_path: Path) -> Callable[[KbSpec], Path]:
    return lambda spec: build(spec, tmp_path / "kb")
