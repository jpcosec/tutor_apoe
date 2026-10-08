"""Episodios que viven dentro de una conversación (docs/sujeto-conversacion-turno.md).

- `AgentRun`: lo que hizo un agente en un turno; vive en el turno.
- `StepVisit`: el tiempo que la conversación pasa en un paso; vive en la conversación. Se abre al
  entrar y se cierra con la transición siguiente; un subflujo sería una visita anidada.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from agents import RunUsageView
from ontology import Episode, Ref


class AgentRun(Episode):
    schema_version: int = 1
    role: str
    messages: int = Field(description="Mensajes que intercambió con el modelo en esta corrida.")
    projection_sha256: str = Field(description="Huella de lo que vio (14 C3).")
    failed: bool = False
    error_class: str | None = Field(
        default=None,
        description="Si falló, la clase: caída del proveedor (`LlmUnavailable`, …) o bug (`InternalFault`).",
    )
    usage: RunUsageView = Field(default_factory=RunUsageView, description="Peticiones, tokens y costo.")


class StepVisit(Episode):
    schema_version: int = 1
    step: str = Field(description="El paso (`Modelo:nombre`).")


def agent_run(
    subject: str,
    turn: str,
    role: str,
    opened_at: datetime,
    messages: int,
    sha256: str,
    failed: bool,
    usage: RunUsageView | None = None,
    error_class: str | None = None,
) -> AgentRun:
    """`turn` es `<conversación>:<n>`; la corrida es `agent_run:<conversación>:<n>:<rol>`."""
    return AgentRun(
        ref=Ref(kind="agent_run", id=f"{turn}:{role}"),
        owner=Ref(kind="subject", id=subject),
        parent=Ref(kind="turn", id=turn),
        opened_at=opened_at,
        closed_at=datetime.now(UTC),
        role=role,
        messages=messages,
        projection_sha256=sha256,
        failed=failed,
        error_class=error_class,
        usage=usage or RunUsageView(),
    )


def move_to(visits: list[StepVisit], step: str | None, subject: str, conversation: str, turn: str) -> None:
    """Cierra la visita abierta si el paso cambió y abre la del paso nuevo; los dos por el turno."""
    current = visits[-1] if visits and visits[-1].is_open else None
    if step is None or (current is not None and current.step == step):
        return
    now, cause = datetime.now(UTC), f"turn:{turn}"
    if current is not None:
        visits[-1] = current.model_copy(update={"closed_at": now, "closed_by": cause})
    visits.append(
        StepVisit(
            ref=Ref(kind="step_visit", id=f"{conversation}:{len(visits) + 1}"),
            owner=Ref(kind="subject", id=subject),
            parent=Ref(kind="conversation", id=conversation),
            opened_by=Ref(kind="turn", id=turn),
            opened_at=now,
            step=step,
        )
    )


def close_visits(visits: list[StepVisit], turn: str) -> None:
    """Al cerrar la conversación, su última visita se cierra con ella (regla 3 de `Episode`)."""
    if visits and visits[-1].is_open:
        visits[-1] = visits[-1].model_copy(
            update={"closed_at": datetime.now(UTC), "closed_by": f"turn:{turn}"}
        )
