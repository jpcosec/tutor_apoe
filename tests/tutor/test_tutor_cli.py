"""`tutor.cli` vía `CliRunner`: los comandos que usa `scripts/docker_smoke.sh` salen con 0 y sin red."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from tutor.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def hash_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUTOR_EMBEDDER", "hash")


def test_kb_validate(kb_root) -> None:
    result = runner.invoke(app, ["kb", "validate", "--kb", str(kb_root)])
    assert result.exit_code == 0, result.output
    assert "KB válida" in result.output


def test_kb_validate_missing_root(tmp_path) -> None:
    result = runner.invoke(app, ["kb", "validate", "--kb", str(tmp_path / "nada")])
    assert result.exit_code != 0


def test_kb_rank(kb_root) -> None:
    result = runner.invoke(app, ["kb", "rank", "--kb", str(kb_root), "qué es la encapsulación en APOS", "--k", "5"])
    assert result.exit_code == 0, result.output
    lines = [line for line in result.output.splitlines() if line.startswith("atom-")]
    assert len(lines) == 5 and any("encapsulation" in line for line in lines)


def test_kb_show(kb_root) -> None:
    result = runner.invoke(app, ["kb", "show", "--kb", str(kb_root), "atom-action-is-a-core-mental-structure-in-apos"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["question"] == "what"
    assert runner.invoke(app, ["kb", "show", "--kb", str(kb_root), "no-existe"]).exit_code == 1


def test_ask_text_and_json(kb_root) -> None:
    args = ["ask", "--kb", str(kb_root), "--model", "test", "¿Qué diferencia una acción de una proceso?"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "mesa · turno 1" in result.output and "semantic" in result.output
    as_json = runner.invoke(app, [*args, "--json"])
    assert as_json.exit_code == 0, as_json.output
    turn = json.loads(as_json.output)
    assert turn["reply"] and turn["mesa"]["atom_ids"] and turn["model"] == "test"


def test_chat_repl_exits(kb_root) -> None:
    result = runner.invoke(app, ["chat", "--kb", str(kb_root), "--model", "test"], input="qué es un esquema\nexit\n")
    assert result.exit_code == 0, result.output
    assert "tutor>" in result.output and "atom-schema" in result.output
