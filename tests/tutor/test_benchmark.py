"""El YAML del benchmark carga, sus ids existen en la KB, y `heuristic`/`embed` corren sobre 3
preguntas; `jev`/`jev_tree` quedan `skipped` sin API key y corren con el cliente fake."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from benchmarks import run as bench  # noqa: E402
from tutor import world  # noqa: E402
from tutor.selector_jev import API_KEY_ENV, FakeJevClient  # noqa: E402

REQUIRED_TOPICS = {
    "topic:action", "topic:process", "topic:object", "topic:schema", "topic:encapsulation",
    "topic:de-encapsulation", "topic:totality", "topic:interiorization", "topic:coordination",
    "topic:reversal", "topic:thematization", "topic:genetic-decomposition", "topic:ace-cycle",
    "topic:isetl", "topic:reflective-abstraction", "topic:rumec", "topic:functions", "topic:groups",
    "topic:elementary-math", "topic:research-paradigm",
}


def test_yaml_loads_and_ids_exist(kb) -> None:
    questions = bench.load_questions()
    assert len(questions) == 20
    assert len({q.id for q in questions}) == 20
    atoms = {a["id"]: a for a in world.list_atoms(kb)}
    for q in questions:
        assert 1 <= len(q.expected_atom_ids) <= 3, q.id
        missing = [i for i in q.expected_atom_ids if i not in atoms]
        assert not missing, (q.id, missing)
        assert q.expected_tags, q.id
        tagged = {t for i in q.expected_atom_ids for t in atoms[i]["tags"]}
        assert set(q.expected_tags) & tagged, (q.id, q.expected_tags, tagged)
    assert REQUIRED_TOPICS <= {t for q in questions for t in q.expected_tags}


def test_heuristic_and_embed_run_on_three_questions(kb, tmp_path: Path) -> None:
    results = bench.run(["heuristic", "embed"], 5, kb=kb, limit=3)
    assert results["n_questions"] == 3
    for name in ("heuristic", "embed"):
        res = results["methods"][name]
        assert res["status"] == "ok", res
        assert len(res["per_question"]) == 3
        assert all(1 <= len(row["top"]) <= 5 for row in res["per_question"])
        assert set(res["metrics"]) == {"hit@1", "hit@5", "mrr", "tag_hit@5", "latency_ms"}
    # la heurística encuentra encapsulación por alias de tag
    heur = results["methods"]["heuristic"]["per_question"]
    assert any(r["hit@k"] for r in heur)
    assert "heuristic" in bench.table(results)


def test_heuristic_port_tags_and_scoring(kb) -> None:
    ranker = bench.HeuristicRanker(world.list_atoms(kb))
    assert ranker.extract_tags("¿Qué es la encapsulación?") == ["topic:encapsulation"]
    assert "topic:process" in ranker.expansions["topic:encapsulation"]
    top = ranker.rank("¿Qué es la encapsulación?", 5)
    assert top and top[0].startswith("atom-encapsulation")


def test_jev_methods_skipped_without_api_key(kb, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    results = bench.run(["jev", "jev_tree"], 5, kb=kb, limit=1)
    for name in ("jev", "jev_tree"):
        assert results["methods"][name]["status"] == "skipped"
        assert API_KEY_ENV in results["methods"][name]["reason"]


def test_jev_methods_run_with_fake_client(kb) -> None:
    results = bench.run(["jev", "jev_tree"], 5, kb=kb, limit=2, jev_client=FakeJevClient())
    for name in ("jev", "jev_tree"):
        res = results["methods"][name]
        assert res["status"] == "ok", res
        assert len(res["per_question"]) == 2
