"""`Episode`: algo con inicio y fin en la vida de un dueño (docs/sujeto-conversacion-turno.md).

Separa dos preguntas: dentro de qué vive (`parent`, forma el árbol del trace) y qué lo causó
(`opened_by`, responde "¿por qué existe esto?"). Las reglas de anidamiento son las mismas para
todos los episodios y se verifican aquí.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import AwareDatetime, Field, field_validator

from ontology.base import OntologyObject
from ontology.ref import Ref


class Episode(OntologyObject):
    owner: Ref = Field(
        description="A quién pertenece: un sujeto casi siempre; un actor o una corrida de evals."
    )
    parent: Ref | None = Field(default=None, description="El episodio que lo contiene; None en la raíz.")
    opened_by: Ref | None = Field(default=None, description="El episodio que lo abrió, si no es su padre.")
    opened_at: AwareDatetime
    closed_at: AwareDatetime | None = None
    closed_by: str | None = Field(default=None, description="Una ref (turno, tool_call, actor) o un motivo.")

    @field_validator("opened_at", "closed_at", mode="before")
    @classmethod
    def _utc(cls, value: object) -> object:
        """Las bases que no guardan zona (SQLite) devuelven UTC sin marcar."""
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    @property
    def is_open(self) -> bool:
        return self.closed_at is None


def nesting_problems(child: Episode, parent: Episode, children_open: bool = False) -> list[str]:
    """Las reglas de todo episodio respecto de su padre; vacío si se cumplen.

    1. Tiene el mismo dueño que su padre. 2. Se abre después que él y se cierra antes, o junto.
    3. Un padre cerrado no tiene hijos abiertos (`children_open` lo informa quien los conoce).
    """
    problems: list[str] = []
    if child.parent != parent.ref:
        problems.append(f"{child.ref}: su padre es {child.parent}, no {parent.ref}")
    if child.owner != parent.owner:
        problems.append(f"{child.ref}: dueño {child.owner} distinto del de su padre {parent.owner}")
    if child.opened_at < parent.opened_at:
        problems.append(f"{child.ref}: se abre antes que su padre")
    if parent.closed_at is not None and (child.closed_at is None or child.closed_at > parent.closed_at):
        problems.append(f"{child.ref}: sigue abierto o se cierra después que su padre")
    if parent.closed_at is not None and children_open:
        problems.append(f"{parent.ref}: cerrado con hijos abiertos")
    return problems


def cause_problems(episode: Episode, cause: Episode) -> list[str]:
    """Regla 4: `opened_by` apunta a un episodio del mismo dueño que ya existía cuando este se abrió."""
    problems: list[str] = []
    if episode.opened_by != cause.ref:
        problems.append(f"{episode.ref}: lo abrió {episode.opened_by}, no {cause.ref}")
    if episode.owner != cause.owner:
        problems.append(f"{episode.ref}: dueño {episode.owner} distinto del de su causa {cause.owner}")
    if cause.opened_at > episode.opened_at:
        problems.append(f"{episode.ref}: su causa {cause.ref} se abrió después que él")
    return problems
