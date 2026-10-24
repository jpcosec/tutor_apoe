"""Approved neutral additions preserve frozen DTO roundtrips and legacy defaults."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cognitive import GuardEvidence, JsonValue, TargetResult
from ontology import Ref


def test_waiting_target_deadline_survives_durable_roundtrip() -> None:
    target = TargetResult(
        target_ref=Ref.parse("machine_instance:waiting"),
        status="no_target",
        retryable=True,
        retry_until="2026-10-06T00:00:00Z",
    )
    restored = TargetResult.model_validate_json(target.model_dump_json())
    assert restored.retry_until == "2026-10-06T00:00:00Z"
    assert restored.retryable is True
    assert restored.status == "no_target"
    with pytest.raises(ValidationError):
        restored.retry_until = None  # type: ignore[misc]


def test_target_legacy_payload_has_no_deadline() -> None:
    target = TargetResult.model_validate(
        {"target_ref": Ref.parse("machine_instance:old"), "status": "delivered"}
    )
    assert target.retry_until is None
    with pytest.raises(ValidationError):
        TargetResult.model_validate(
            {
                "target_ref": Ref.parse("machine_instance:old"),
                "status": "no_target",
                "retry_until": {"untrusted": "date"},
            }
        )


def test_guard_evidence_pins_snapshot_without_mutable_aliases() -> None:
    checks: list[JsonValue] = [True, 1]
    value: dict[str, JsonValue] = {"checks": checks}
    evidence = GuardEvidence(
        path=("world", "observation:checked", "value"),
        present=True,
        value=value,
        result=True,
        snapshot_hash="a" * 64,
    )
    checks.append(False)
    restored = GuardEvidence.model_validate_json(evidence.model_dump_json())
    assert restored.value == {"checks": [True, 1]}
    assert restored.snapshot_hash == "a" * 64
    with pytest.raises(ValidationError):
        restored.snapshot_hash = "b" * 64  # type: ignore[misc]


def test_guard_legacy_payload_and_hash_type() -> None:
    assert GuardEvidence(path=("x",), present=False, result=False).snapshot_hash is None
    with pytest.raises(ValidationError):
        GuardEvidence.model_validate(
            {"path": ["x"], "present": True, "result": True, "snapshot_hash": ["hash"]}
        )
