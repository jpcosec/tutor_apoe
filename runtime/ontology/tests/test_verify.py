from ontology import OntologyObject, Ref, verify_refs


class Trace(OntologyObject):
    schema_version: int = 1
    steps: list[Ref]
    tools: list[Ref]
    subject: Ref


KNOWN_STEPS = {
    "kb:ConversationStep:step-demo-respuesta@r1",
    "kb:ConversationStep:step-demo-pagada@r1",
}


def trace() -> Trace:
    return Trace(
        ref=Ref.parse("turn:s-1:3"),
        steps=[
            Ref.parse("kb:ConversationStep:step-demo-respuesta@r1"),
            Ref.parse("kb:ConversationStep:step-que-no-existe@r1"),
            Ref.parse("kb:ConversationStep:step-demo-respuesta@r1"),
        ],
        tools=[Ref.parse("tool:registrar_status")],
        subject=Ref.parse("subject:4471"),
    )


def test_paso_inexistente_queda_en_missing() -> None:
    report = verify_refs(
        trace(),
        {"kb": lambda ref: str(ref) in KNOWN_STEPS, "tool": lambda ref: ref.id == "registrar_status"},
    )

    assert [str(ref) for ref in report.missing] == ["kb:ConversationStep:step-que-no-existe@r1"]
    assert report.unresolved_kinds == ["subject"]
    assert report.checked == 3  # refs únicas de familias con resolutor
    assert report.ok is False


def test_sin_resolutores_nada_falta() -> None:
    report = verify_refs(trace(), {})

    assert report.ok is True
    assert report.checked == 0
    assert report.unresolved_kinds == ["kb", "tool", "subject"]


def test_el_reporte_es_serializable() -> None:
    report = verify_refs(trace(), {"kb": lambda ref: False})

    dumped = report.model_dump(mode="json")

    assert dumped["ok"] is False
    assert dumped["missing"][0] == {
        "kind": "kb",
        "id": "ConversationStep:step-demo-respuesta",
        "release_id": "r1",
    }
