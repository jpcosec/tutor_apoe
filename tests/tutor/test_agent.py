"""`tutor.agent`: la mesa sale del `ContextRouter` real, el turno responde sin red con el modelo de
prueba, retiene entre turnos, respeta el hook `Selector` y resuelve modelos por nombre sin red."""

from __future__ import annotations

import pytest
from pydantic_ai.models import Model
from pydantic_ai.models.test import TestModel

from tutor import world
from tutor.agent import Conversation, TurnResult, answer, build_agent, build_context, instructions_for, resolve_model

QUESTION = "¿Qué diferencia una acción de un proceso?"
ACTION = "atom-action-is-a-core-mental-structure-in-apos"
FOUR = "atom-apos-defines-four-core-mental-structures"


def _tags(kb, atom_id: str) -> set[str]:
    return set((world.get_atom(kb, atom_id) or {}).get("tags", []))


def test_answer_with_test_model(kb) -> None:
    turn = answer(QUESTION, kb=kb, model="test")
    assert isinstance(turn, TurnResult)
    assert turn.reply.strip() and turn.model == "test"
    assert turn.usage and turn.usage["requests"] == 1
    mesa = turn.mesa
    assert mesa["query"] == QUESTION and mesa["atom_ids"] and len(mesa["items"]) <= 8
    assert {"atom_id", "title", "score", "why", "role"} <= set(mesa["items"][0])
    topical = [
        i["atom_id"]
        for i in mesa["items"]
        if _tags(kb, i["atom_id"]) & {"topic:action", "topic:process", "topic:action-to-process"}
    ]
    assert topical, mesa["items"]
    types = {entry["type"] for entry in mesa["reasoning_log"]}
    assert {"query", "ledger", "candidate_scores", "added_atom_ids", "retained_atom_ids"} <= types
    # el modelo de prueba cita la mesa
    assert mesa["atom_ids"][0] in turn.reply


def test_second_turn_retains_from_first(kb) -> None:
    first = answer(QUESTION, kb=kb, model="test")
    second = answer("¿y cómo se interioriza?", kb=kb, model="test", previous=first)
    assert second.mesa["turn"] == 2
    retained = second.mesa["retained_atom_ids"]
    assert retained and set(retained) <= set(first.mesa["atom_ids"])
    by_id = {i["atom_id"]: i for i in second.mesa["items"]}
    assert all(by_id[a]["role"] == "retained" and "retained_from_previous" in by_id[a]["why"] for a in retained)
    assert second.mesa["added_atom_ids"], "un turno nuevo también trae átomos nuevos"


class FixedSelector:
    def __init__(self, ids: list[str]) -> None:
        self.ids, self.calls = ids, []

    def select(self, role, question, step, pool):
        self.calls.append((role, question, step, len(pool)))
        return list(self.ids)


class NullSelector:
    def select(self, role, question, step, pool):
        return None


def test_selector_hook_is_respected(kb) -> None:
    selector = FixedSelector([ACTION, f"KnowledgeAtom:{FOUR}"])
    mesa = build_context(kb, "hola", selector=selector, k=4)
    assert selector.calls and selector.calls[0][0] == "tutor" and selector.calls[0][3] >= 2
    llm_items = [i for i in mesa["items"] if i["role"] == "llm"]
    assert {i["atom_id"] for i in llm_items} == {ACTION, FOUR}
    assert dict(e for e in ((x["type"], x["detail"]) for x in mesa["reasoning_log"]))["selector"] == "llm"
    # None → heurística, no vacío
    fallback = build_context(kb, QUESTION, selector=NullSelector(), k=4)
    assert fallback["items"] and all(i["role"] != "llm" for i in fallback["items"])


def test_build_agent_instructions_and_tools(kb) -> None:
    text = instructions_for(kb, "tutor")
    assert "APOS" in text and "No inventes" in text and "show_atom" in text
    mesa = build_context(kb, QUESTION, k=3)
    agent = build_agent(kb, model=TestModel(call_tools=[]), mesa_items=mesa["items"])
    assert {t for t in agent._function_toolset.tools} == {"show_atom", "explore"}  # noqa: SLF001
    result = agent.run_sync(QUESTION)
    assert result.output


def test_tools_run_with_test_model_calling_them(kb) -> None:
    turn = answer("¿Qué es la encapsulación?", kb=kb, model=TestModel())
    assert turn.reply and turn.usage["requests"] == 2
    assert turn.model == "test:test"


def test_show_atom_and_explore_scoped_to_projection(kb) -> None:
    from tutor.agent import TutorTools

    tools = TutorTools(kb, "tutor")
    shown = tools.show_atom(f"[{ACTION}]")
    assert shown.startswith(f"[KnowledgeAtom:{ACTION}]") and "Acción" in shown
    assert tools.reads == [ACTION]
    assert "fuera de tu porción" in tools.show_atom("agent-tutor-apos")
    assert "fuera de tu porción" in tools.show_atom("no-existe")
    lines = tools.explore("encapsulación", max_results=3).splitlines()
    assert len(lines) == 3 and any("encapsulation" in line for line in lines)


def test_conversation_keeps_history(kb) -> None:
    chat = Conversation(kb=kb, model="test")
    chat.ask("qué es un esquema")
    second = chat.ask("¿y la tematización?")
    assert len(chat.turns) == 2 and chat.last is second
    assert len(chat.message_history) == 4
    assert second.mesa["retained_atom_ids"]


def test_resolve_model_paths_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    assert isinstance(resolve_model("test"), Model)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    gemini = resolve_model("google-gla:gemini-2.5-flash")
    assert isinstance(gemini, Model) and gemini.model_name == "gemini-2.5-flash"
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    openai = resolve_model("openai:gpt-4o-mini")
    assert isinstance(openai, Model) and openai.model_name == "gpt-4o-mini" and openai.system == "openai"
