"""GuardExpr y evidencia de guard (api-canonica §guard y criterio de Goal).

Declarativo y cerrado: sin eval ni Python embebido. Extensiones de guard son
handlers registrados y versionados (ver state_machine.guards).
"""

from __future__ import annotations

from typing import Literal, get_args

from pydantic import model_validator

from cognitive._base import FrozenModel
from cognitive.jsons import JsonValue

type GuardOp = Literal["eq", "ne", "gt", "ge", "lt", "le", "exists", "all", "any", "not"]
GUARD_OPS: frozenset[str] = frozenset(
    get_args(Literal["eq", "ne", "gt", "ge", "lt", "le", "exists", "all", "any", "not"])
)

#: Operaciones de comparación: exigen path + value, sin children.
COMPARISON_OPS = frozenset({"eq", "ne", "gt", "ge", "lt", "le"})
#: Operaciones booleanas: exigen children no vacíos, sin path/value.
BOOL_OPS = frozenset({"all", "any"})


class GuardExpr(FrozenModel):
    """Predicado declarativo sobre un snapshot autorizado.

    Reglas (api-canonica):
    - comparaciones exigen `path` + `value` explícito, sin `children`;
    - `exists` exige `path`, sin value ni children;
    - `all`/`any` exigen `children` no vacíos, sin path ni value;
    - `not` exige exactamente un hijo;
    - `path` es tupla de claves de Mapping; nunca string con puntos.
    """

    op: GuardOp
    path: tuple[str, ...] = ()
    value: JsonValue = None
    children: tuple[GuardExpr, ...] = ()

    @model_validator(mode="after")
    def _campos_aplicables(self) -> GuardExpr:
        value_set = "value" in self.model_fields_set
        if self.op in COMPARISON_OPS:
            if not self.path:
                raise ValueError(f"op {self.op!r} exige path no vacío")
            if self.children:
                raise ValueError(f"op {self.op!r} no admite children")
            if not value_set:
                raise ValueError(f"op {self.op!r} exige value explícito")
        elif self.op == "exists":
            if not self.path:
                raise ValueError("op 'exists' exige path no vacío")
            if self.children:
                raise ValueError("op 'exists' no admite children")
            if value_set:
                raise ValueError("op 'exists' no admite value")
        elif self.op in BOOL_OPS:
            if self.path:
                raise ValueError(f"op {self.op!r} no admite path")
            if not self.children:
                raise ValueError(f"op {self.op!r} exige children no vacío")
            if value_set:
                raise ValueError(f"op {self.op!r} no admite value")
        elif self.op == "not":
            if self.path:
                raise ValueError("op 'not' no admite path")
            if len(self.children) != 1:
                raise ValueError("op 'not' exige exactamente un hijo")
            if value_set:
                raise ValueError("op 'not' no admite value")
        return self


class GuardEvidence(FrozenModel):
    """Registro de una evaluación de path: valor anonimizado y resultado."""

    path: tuple[str, ...]
    present: bool
    value: JsonValue = None
    result: bool
    snapshot_hash: str | None = None
