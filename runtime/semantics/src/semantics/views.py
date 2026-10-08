"""Las vistas con que la ontología renderiza lo que entra a un prompt (spec 15 §6.1, O1)."""

from __future__ import annotations

from kb import View, table_view
from tools import EntityType

PAIRS = {"campo": "Nombre del dato.", "valor": "Su valor."}
PROBLEMS = {"campo": "Dato que falló.", "problema": "Qué estuvo mal."}
PROFILE = {"dato": "Lo que se sabe de la persona.", "valor": "Su valor."}
TRACE = {
    "turno": "Número de turno.",
    "mensaje": "Lo que escribió la persona.",
    "paso": "Paso antes y después del turno.",
    "decision": "Qué decidió el orquestador.",
    "tool": "Tool ejecutada y su estado.",
}

ACTION_VIEW = table_view("ActionView", PAIRS)
DATA_VIEW = table_view("DataView", PAIRS, "#### Otros datos")
ERRORS_VIEW = table_view("ErrorsView", PROBLEMS, "#### Problemas")
PROFILE_VIEW = table_view("ProfileView", PROFILE)
TRACE_VIEW = table_view("TraceView", TRACE)
STATIC_VIEWS: tuple[View, ...] = (ACTION_VIEW, DATA_VIEW, ERRORS_VIEW, PROFILE_VIEW, TRACE_VIEW)


def rows_view(entity: EntityType) -> View:
    """La tabla de filas de una entidad: su clave y sus campos, en el orden del `EntityDoc`."""
    columns = {"ref": "Cómo citar esta fila.", entity.key: "Clave de la fila."} | {
        name: entity.descriptions.get(name) or name for name in entity.fields
    }
    return table_view(f"Rows_{entity.name}", columns, f"#### {entity.name}")
