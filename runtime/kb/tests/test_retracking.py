"""Re-extracción (spec 01 §6.3): `--dry-run` mide el alcance sin escribir en el store.

Un cambio de esquema deja atrás el derivado de cada documento, así que antes de propagarlo hay
que saber cuántos toca. Previsualizar es la diferencia entre medir y arriesgar el store.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from kb.cli import app
from kb.retracking import retrack
from make_fixture import KbSpec, minimal

runner = CliRunner()

STALE = "Note:nota-a"


def _desalineado(root: Path) -> Path:
    """Edita el `.md` sin re-extraer: el derivado del store queda atrás del archivo."""
    md = root / "notes/nota-a.md"
    md.write_text(md.read_text(encoding="utf-8").replace("A.", "A, con otro cuerpo."), encoding="utf-8")
    return root


def test_dry_run_informa_sin_tocar_el_store(build_kb: Callable[[KbSpec], Path]) -> None:
    root = _desalineado(build_kb(minimal()))
    store = root / ".sldb"
    antes = {p: p.read_bytes() for p in sorted(store.rglob("*")) if p.is_file()}

    report = retrack(root, dry_run=True)

    assert report.would_retrack == [STALE]
    assert report.retracked == []
    assert {p: p.read_bytes() for p in sorted(store.rglob("*")) if p.is_file()} == antes


def test_dry_run_y_retrack_coinciden(build_kb: Callable[[KbSpec], Path]) -> None:
    root = _desalineado(build_kb(minimal()))

    anunciado = retrack(root, dry_run=True).would_retrack
    hecho = retrack(root).retracked

    assert anunciado == hecho == [STALE]
    assert retrack(root, dry_run=True).would_retrack == []


def test_cli_dry_run_no_escribe(build_kb: Callable[[KbSpec], Path]) -> None:
    root = _desalineado(build_kb(minimal()))

    result = runner.invoke(app, ["retrack", str(root), "--dry-run"])

    assert result.exit_code == 0
    assert json.loads(result.output)["would_retrack"] == [STALE]
    assert json.loads(runner.invoke(app, ["retrack", str(root), "--dry-run"]).output)["would_retrack"] == [
        STALE
    ]
