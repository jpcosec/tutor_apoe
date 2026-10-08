"""03 I5: una tool con `requires_identity` no corre sin el vínculo verificado del sujeto."""

from __future__ import annotations

from typing import ClassVar, Literal

import pytest
from pydantic import BaseModel

from tools import IdentityCheck, IdentityRequirement, ToolCatalog, ToolContext, ToolOutcome, ToolResult
from tools.contract import Tool
from tools.toolset import execute


class Links:
    """Los vínculos de 02: `ana` tiene verificado el WhatsApp +56911111111."""

    def verify(self, subject_key: str, kind: str, claimed: str) -> IdentityCheck:
        loaded = {("ana", "whatsapp"): "+56911111111"}.get((subject_key, kind))
        return IdentityCheck(provided=loaded is not None, verified=loaded == claimed)


class Args(BaseModel):
    telefono: str


class Consultar(Tool):
    name: ClassVar[str] = "consultar"
    description: ClassVar[str] = "Consulta algo privado."
    Args: ClassVar[type[BaseModel]] = Args
    kind: ClassVar[Literal["read", "write", "external"]] = "read"
    requires_identity: ClassVar[IdentityRequirement | None] = IdentityRequirement(
        kind="whatsapp", arg="telefono"
    )

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, context: ToolContext, args: BaseModel) -> ToolResult:
        self.calls += 1
        return ToolResult(data={"ok": True})


def run(subject: str, telefono: str, links: object | None = None) -> tuple[Consultar, ToolOutcome]:
    tool = Consultar()
    ports = {} if links is None else {"identity_links": links}
    outcome = execute(
        tool, ToolContext(session_id=subject, turn_id="t", ports=ports), Args(telefono=telefono)
    )
    return tool, outcome


@pytest.mark.parametrize(
    ("subject", "telefono", "links", "status", "identity"),
    [
        ("ana", "+56911111111", Links(), "ok", (True, True)),
        ("ana", "+56999999999", Links(), "rejected", (True, False)),  # lo afirmado no coincide
        ("beto", "+56911111111", Links(), "rejected", (False, False)),  # sin vínculo cargado
        ("ana", "+56911111111", None, "rejected", (False, False)),  # sin puerto: no se ejecuta
    ],
)
def test_solo_corre_con_el_vinculo_verificado(
    subject: str, telefono: str, links: object | None, status: str, identity: tuple[bool, bool]
) -> None:
    tool, outcome = run(subject, telefono, links)

    assert outcome.status == status
    assert outcome.identity is not None
    assert (outcome.identity.provided, outcome.identity.verified) == identity
    assert tool.calls == (1 if status == "ok" else 0)
    if status == "rejected":
        assert outcome.error_class == "identity_not_verified"


def test_el_argumento_de_identidad_debe_estar_en_args() -> None:
    class Mal(Consultar):
        name: ClassVar[str] = "mal"
        requires_identity: ClassVar[IdentityRequirement | None] = IdentityRequirement(
            kind="whatsapp", arg="rut"
        )

    with pytest.raises(ValueError, match="no está en Args"):
        ToolCatalog([Mal()])
