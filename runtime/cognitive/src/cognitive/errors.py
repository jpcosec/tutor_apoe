"""Errores de dominio del contrato canónico (api-canonica).

Los consumidores (actions/actors/world) toleran excepciones con estos nombres;
el motor y los repositorios in-memory las lanzan con evidencia suficiente.
"""

from __future__ import annotations

from cognitive.scope import Scope
from ontology import Ref


class CognitiveError(Exception):
    """Raíz de los errores del contrato canónico."""


class GuardTypeError(CognitiveError):
    """Tipos incompatibles en una comparación de guard; no hay coerción."""

    def __init__(self, path: tuple[str, ...], detail: str) -> None:
        super().__init__(f"tipos incompatibles en path {'.'.join(path) or '<vacío>'}: {detail}")
        self.path = path
        self.detail = detail


class GuardCompileError(CognitiveError):
    """GuardExpr inválido al compilar/validar una definición."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class UnknownGuardOpError(GuardCompileError):
    """Operación de guard no registrada; extensiones desconocidas impiden arrancar."""


class UnknownEventError(CognitiveError):
    """El evento no está admitido por ninguna transición de la definición."""

    def __init__(self, event_type: str, definition_ref: Ref) -> None:
        super().__init__(f"evento {event_type!r} no admitido por {definition_ref}")
        self.event_type = event_type
        self.definition_ref = definition_ref


class InvalidEventError(CognitiveError):
    """El payload no cumple el JSON schema registrado para el tipo de evento."""

    def __init__(self, event_type: str, errors: tuple[str, ...]) -> None:
        super().__init__(f"payload inválido para {event_type!r}: {errors}")
        self.event_type = event_type
        self.errors = errors


class EventCollisionError(CognitiveError):
    """Mismo event id con payload/source distintos: no hay dedupe silencioso."""

    def __init__(self, event_id: str, instance_ref: Ref) -> None:
        super().__init__(f"evento {event_id!r} ya procesado para {instance_ref} con payload/source distintos")
        self.event_id = event_id
        self.instance_ref = instance_ref


class ScopeMismatchError(CognitiveError):
    """La instancia pertenece a otro cliente/scope."""

    def __init__(self, instance_ref: Ref, client_id: str) -> None:
        super().__init__(f"instancia {instance_ref} no pertenece al cliente {client_id!r}")
        self.instance_ref = instance_ref
        self.client_id = client_id


class DefinitionMismatchError(CognitiveError):
    """La instancia está fijada a una definición/hash distinto del usado."""

    def __init__(self, instance_ref: Ref, expected: str, actual: str) -> None:
        super().__init__(f"instancia {instance_ref}: hash de definición {actual!r} != esperado {expected!r}")
        self.instance_ref = instance_ref
        self.expected = expected
        self.actual = actual


class UnreachableStateError(CognitiveError):
    """Estado inalcanzable desde initial_state; error en v0.1."""

    def __init__(self, state: str, definition_ref: Ref) -> None:
        super().__init__(f"estado {state!r} inalcanzable en {definition_ref}")
        self.state = state
        self.definition_ref = definition_ref


class TransitionRejected(CognitiveError):
    """Ningún candidato habilitado; la instancia no cambia revisión."""

    def __init__(
        self,
        instance_ref: Ref,
        event_id: str,
        reasons: tuple[str, ...],
        guard_evidence: tuple[object, ...] = (),
    ) -> None:
        super().__init__(f"transición rechazada para {instance_ref} evento {event_id}: {reasons}")
        self.instance_ref = instance_ref
        self.event_id = event_id
        self.reasons = reasons
        self.guard_evidence = guard_evidence


class AmbiguousTransition(CognitiveError):
    """Empate de prioridad entre candidatos habilitados."""

    def __init__(self, instance_ref: Ref, event_id: str, transition_refs: tuple[str, ...]) -> None:
        super().__init__(f"transición ambigua para {instance_ref} evento {event_id}: {transition_refs}")
        self.instance_ref = instance_ref
        self.event_id = event_id
        self.transition_refs = transition_refs


class RevisionConflictError(CognitiveError):
    """CAS sobre revision falla (concurrencia humana/ejecución)."""

    def __init__(self, store: str, ref: Ref, expected: int, actual: int | None) -> None:
        super().__init__(f"{store} {ref}: revision esperada {expected}, actual {actual}")
        self.store = store
        self.ref = ref
        self.expected = expected
        self.actual = actual


class IdempotencyCollisionError(CognitiveError):
    """Misma clave idempotente + scope con payload distinto."""

    def __init__(self, key: str, scope: Scope) -> None:
        super().__init__(f"colisión de idempotencia {key!r} en scope {scope.client_id!r}")
        self.key = key
        self.scope = scope

    @property
    def scope_id(self) -> str:
        return self.scope.client_id


class AuthorizationDeniedError(CognitiveError):
    """Capacidad/scope no autorizados."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class CardinalityViolationError(CognitiveError):
    """La definición no admite otra instancia activa para el mismo owner."""

    def __init__(self, definition_ref: Ref, owner_ref: Ref) -> None:
        super().__init__(
            f"cardinalidad one_active_per_owner: ya existe instancia activa de "
            f"{definition_ref} para {owner_ref}"
        )
        self.definition_ref = definition_ref
        self.owner_ref = owner_ref
