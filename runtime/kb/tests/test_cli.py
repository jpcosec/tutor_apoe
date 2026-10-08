from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from kb.cli import app
from make_fixture import Doc, KbSpec, minimal, relation_doc

runner = CliRunner()


def test_validate_valida(minimal_root: Path) -> None:
    result = runner.invoke(app, ["validate", str(minimal_root)])

    assert result.exit_code == 0
    assert result.output == ""


def test_validate_invalida_imprime_cinco_columnas(build_kb: Callable[[KbSpec], Path]) -> None:
    spec = minimal()
    spec.docs.append(relation_doc("Note:nota-a", "Note:no-existe"))

    result = runner.invoke(app, ["validate", str(build_kb(spec))])

    assert result.exit_code == 1
    columns = result.output.splitlines()[0].split("  ")
    assert columns[:2] == ["V6", "sldb"]
    assert len(columns) >= 5


def test_query_show_stats_materialize(minimal_root: Path, tmp_path: Path) -> None:
    query = runner.invoke(app, ["query", str(minimal_root), "--model", "Note"])
    exact = runner.invoke(app, ["query", str(minimal_root), "--model", "Note", "--exact"])
    by_tag = runner.invoke(app, ["query", str(minimal_root), "--tag", "topic:dos", "--eligible"])
    family = runner.invoke(app, ["query", str(minimal_root), "--family", "self"])
    show = runner.invoke(app, ["show", str(minimal_root), "nota-a"])
    stats = runner.invoke(app, ["stats", str(minimal_root)])
    output = tmp_path / "kb.md"
    materialized = runner.invoke(app, ["materialize", str(minimal_root), "-o", str(output)])
    printed = runner.invoke(app, ["materialize", str(minimal_root)])

    assert json.loads(query.output) == ["Note:nota-a", "SpecialNote:nota-b"]
    assert json.loads(exact.output) == ["Note:nota-a"]
    assert json.loads(by_tag.output) == ["SpecialNote:nota-b"]
    assert json.loads(family.output) == ["Tool:tool-x"]
    assert json.loads(show.output)["name"] == "nota-a"
    assert json.loads(stats.output)["documents"] == 3
    assert materialized.exit_code == 0
    assert output.read_text() == printed.output


def test_query_exige_un_selector(minimal_root: Path) -> None:
    result = runner.invoke(app, ["query", str(minimal_root), "--model", "Note", "--tag", "x"])

    assert result.exit_code != 0


def test_lenient_sigue_con_errores(build_kb: Callable[[KbSpec], Path]) -> None:
    spec = minimal()
    spec.docs.append(Doc("Note", "notes/nota-c.md", {"id": "otro", "title": "c", "tags": [], "body": "x"}))
    root = build_kb(spec)

    strict = runner.invoke(app, ["stats", str(root)])
    lenient = runner.invoke(app, ["stats", str(root), "--lenient"])

    assert strict.exit_code == 1
    assert strict.output.startswith("V2  kb  Note:nota-c")
    assert json.loads(lenient.output)["documents"] == 4


def test_kb_inexistente(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate", str(tmp_path)])

    assert result.exit_code == 1
