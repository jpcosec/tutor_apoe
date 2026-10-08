"""`JevSelector` cumple el `Selector` de `runtime/context`, ordena por noul, cae a None sin
cliente; `JevTreeRouter` con el cliente fake llega a las hojas de la rama esperada. Sin red."""

from __future__ import annotations

import inspect

import pytest

from tutor import world
from tutor.selector_jev import (
    API_KEY_ENV,
    FakeJevClient,
    JevSelector,
    JevTreeRouter,
    default_client,
    make_choice,
    make_noul,
)

POOL = [
    ("atom-encapsulation-treats-a-process-as-a-static-entity", "La encapsulación permite tratar un proceso como una entidad estática: el individuo ve el proceso como una totalidad."),
    ("atom-rumec-was-a-major-community-in-apos-development", "RUMEC fue una comunidad decisiva en el desarrollo histórico de APOS."),
    ("atom-encapsulation-is-reported-as-one-of-the-most-difficult-mechanisms", "La encapsulación se reporta como uno de los mecanismos más difíciles para los estudiantes."),
    ("atom-isetl-functions-as-a-pedagogical-tool-in-apos-instruction", "ISETL es un lenguaje de programación usado en actividades basadas en APOS."),
]
QUESTION = "¿Qué es la encapsulación y por qué es tan difícil para los estudiantes?"


def test_select_matches_protocol_signature() -> None:
    from context.selector import Selector

    expected = inspect.signature(Selector.select)
    actual = inspect.signature(JevSelector.select)
    assert list(actual.parameters) == list(expected.parameters) == ["self", "role", "question", "step", "pool"]
    selector: Selector = JevSelector(client=FakeJevClient())  # estructural: tipa como Selector
    assert selector.select("tutor", "x", None, []) == []


def test_select_returns_sorted_ids_above_threshold() -> None:
    client = FakeJevClient()
    selector = JevSelector(client=client, threshold=0.5, k=3)
    chosen = selector.select("tutor", QUESTION, None, POOL)
    assert chosen is not None
    assert chosen[0] == "atom-encapsulation-is-reported-as-one-of-the-most-difficult-mechanisms"
    assert set(chosen) == {
        "atom-encapsulation-is-reported-as-one-of-the-most-difficult-mechanisms",
        "atom-encapsulation-treats-a-process-as-a-static-entity",
    }
    assert len(client.calls) == len(POOL)  # un Noul por candidato
    scored = dict(selector.score(QUESTION, POOL))
    assert all(scored[a] >= scored[b] for a, b in zip(chosen, chosen[1:]))
    assert scored["atom-rumec-was-a-major-community-in-apos-development"] < 0.5
    state = client.calls[0]["state"]
    assert state["student_question"] == QUESTION and "candidate_atom" in state
    assert client.calls[0]["model"] == selector.model


def test_select_respects_k_and_pool_cap() -> None:
    selector = JevSelector(client=FakeJevClient(), threshold=0.0, k=2)
    pool = [(f"atom-{i}", "encapsulación difícil estudiantes") for i in range(40)]
    chosen = selector.select("tutor", QUESTION, "paso-1", pool)
    assert chosen is not None and len(chosen) == 2
    assert selector.score(QUESTION, pool) is not None and len(selector.score(QUESTION, pool)) == 30


def test_select_returns_none_without_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    assert default_client() is None
    selector = JevSelector()  # client=None y sin API key → None (el ruteador cae a heurística)
    assert selector.client is None
    assert selector.select("tutor", QUESTION, None, POOL) is None
    assert selector.select("tutor", QUESTION, None, []) == []


def test_select_returns_none_on_client_error() -> None:
    class Broken:
        def system_one(self, state, questions, *, model=None):
            raise ConnectionError("sin red")

    assert JevSelector(client=Broken()).select("tutor", QUESTION, None, POOL) is None


def test_questions_build_with_or_without_sdk() -> None:
    noul = make_noul("¿sí?", {"true": "a", "false": "b"})
    choice = make_choice("¿cuál?", {"c0": {"title": "x"}, "c1": None})
    for q, kind in ((noul, "noul"), (choice, "choice")):
        spec = q if isinstance(q, dict) else q.model_dump()
        assert spec["type"] == kind and spec["instructions"]


def test_tree_router_reaches_expected_branch_leaves(kb) -> None:
    client = FakeJevClient()
    router = JevTreeRouter(kb, client=client)
    leaves = router.route(QUESTION)
    assert leaves is not None and 1 <= len(leaves) <= router.beam_width
    ids = [atom_id for atom_id, _ in leaves]
    probs = [p for _, p in leaves]
    assert probs == sorted(probs, reverse=True) and all(0 < p <= 1 for p in probs)
    encapsulation = {d["id"] for d in world.children(kb, "branch-apos-mechanisms-encapsulation")}
    assert ids[0] in encapsulation, leaves
    assert all(world.get_atom(kb, atom_id)["model"] != "BranchNode" for atom_id in ids)
    # un Choice por nodo expandido, con opciones c0..cN que mapean a hijos reales
    assert client.calls and all("rama" in call["questions"] for call in client.calls)


def test_tree_router_none_without_client(kb, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    assert JevTreeRouter(kb).route(QUESTION) is None
