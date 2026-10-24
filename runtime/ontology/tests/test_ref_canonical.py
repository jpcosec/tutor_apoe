"""Familias canónicas de una sola componente (api-canonica §identidad)."""

from __future__ import annotations

import pytest

from ontology import Kind, Ref, RefFormatError


@pytest.mark.parametrize(
    "text",
    [
        "machine_instance:consent-1",
        "process_instance:p-1",
        "goal_instance:g-1",
        "self_assignment:sa-1",
        "action_execution:ae-1",
        "knowledge_activation:ka-1",
        "knowledge_version:kv-1",
        "observation:o-1",
        "receipt:r-1",
        "review_request:rr-1",
        "delivery:d-1",
        "release:rel-1",
        "deployment:dep-1",
        "repair_case:rc-1",
    ],
)
def test_familias_canonicas_roundtrip(text: str) -> None:
    ref = Ref.parse(text)
    assert str(ref) == text
    assert ref.kind == text.split(":", 1)[0]


def test_familias_canonicas_en_kind() -> None:
    for fam in (
        "machine_instance",
        "process_instance",
        "goal_instance",
        "self_assignment",
        "action_execution",
        "knowledge_activation",
        "knowledge_version",
        "observation",
        "receipt",
        "review_request",
        "delivery",
        "release",
        "deployment",
        "repair_case",
    ):
        assert fam in Kind.__args__


def test_una_sola_componente() -> None:
    with pytest.raises(RefFormatError):
        Ref.parse("machine_instance:a:b")
    with pytest.raises(RefFormatError):
        Ref.parse("goal_instance:")


def test_sin_release_para_no_kb() -> None:
    ref = Ref.parse("machine_instance:x")
    assert ref.release_id is None
    # require_release solo aplica a refs kb que se persisten fuera de la KB.
    assert ref.require_release() is ref
