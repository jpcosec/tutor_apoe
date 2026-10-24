"""`Episode`: dueño, contenedor, causa y tiempo; las reglas de anidamiento."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ontology import Episode, Ref, nesting_problems

T0 = datetime(2026, 9, 28, 10, 0, tzinfo=UTC)
SUBJECT = Ref(kind="subject", id="s-7")


def episode(ref: str, parent: Ref | None, opened: int, closed: int | None = None, **extra: object) -> Episode:
    return Episode(
        ref=Ref.parse(ref),
        schema_version=1,
        owner=SUBJECT,
        parent=parent,
        opened_at=T0 + timedelta(minutes=opened),
        closed_at=None if closed is None else T0 + timedelta(minutes=closed),
        **extra,  # pyright: ignore[reportArgumentType]
    )


def test_un_hijo_bien_anidado_no_tiene_problemas() -> None:
    conversation = episode("conversation:a", SUBJECT, 0, 30)
    turn = episode("turn:a:1", conversation.ref, 5, 6)

    assert nesting_problems(turn, conversation) == []


def test_las_reglas_de_anidamiento() -> None:
    conversation = episode("conversation:a", SUBJECT, 10, 30)
    early = episode("turn:a:1", conversation.ref, 5, 6)
    open_child = episode("turn:a:2", conversation.ref, 12)
    stranger = episode("turn:a:3", conversation.ref, 12, 13).model_copy(
        update={"owner": Ref(kind="subject", id="otra")}
    )

    assert any("antes que su padre" in p for p in nesting_problems(early, conversation))
    assert any("sigue abierto" in p for p in nesting_problems(open_child, conversation))
    assert any("dueño" in p for p in nesting_problems(stranger, conversation))


def test_dentro_de_que_vive_y_que_lo_causo_son_campos_distintos() -> None:
    turn = Ref.parse("turn:a:2")
    promise = episode("record:promesa:1", SUBJECT, 7, opened_by=Ref(kind="tool_call", id="01j9"))

    assert promise.parent == SUBJECT
    assert promise.opened_by == Ref(kind="tool_call", id="01j9")
    assert promise.opened_by != turn
    assert promise.is_open


def test_una_fecha_sin_zona_se_lee_como_utc() -> None:
    naive = Episode(
        ref=Ref.parse("conversation:a"),
        schema_version=1,
        owner=SUBJECT,
        parent=SUBJECT,
        opened_at=datetime(2026, 9, 28, 10, 0),  # pyright: ignore[reportArgumentType]
    )

    assert naive.opened_at == T0


def test_regla_4_la_causa_es_del_mismo_dueno_y_anterior() -> None:
    from ontology import cause_problems

    call = episode("tool_call:c1", None, 0)
    event = episode("step_visit:c:1", None, 1, opened_by=call.ref)
    early = event.model_copy(update={"opened_at": T0 - timedelta(minutes=1)})
    foreign = event.model_copy(update={"owner": Ref(kind="subject", id="otro")})

    assert cause_problems(event, call) == []
    assert any("después" in p for p in cause_problems(early, call))
    assert any("dueño" in p for p in cause_problems(foreign, call))
