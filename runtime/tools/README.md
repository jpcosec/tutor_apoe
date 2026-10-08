# tools (spec 03)

Módulo 03: las tools de negocio. Su interfaz tiene tres audiencias; cada bloque de `__all__` dice
cuál es la suya.

Contrato: [`specs/spec-03-tools.md`](../../specs/spec-03-tools.md)

| Si buscás | Andá a |
|---|---|
| qué hace y qué queda afuera | spec §1, §2 |
| lo que el módulo exige a sus entradas | spec §4 |
| las invariantes | spec §5 |
| el contrato exportado | spec §7 · [`src/tools/__init__.py`](src/tools/__init__.py) |
| cómo se prueba | spec §8 · [`tests/`](tests/) |
| límites de implementación | spec §9 |

## Cómo está armado

| Archivo | Qué hace |
|---|---|
| `contract.py` | `Conflict`, `ErrorClass` y el contrato de una tool |
| `toolset.py` | `business_toolset`: las tools como toolset de Pydantic AI (valida `Args`, pide corrección, plazo por tool) |
| `runner.py` | `ToolRunner` — llamadas sin modelo |
| `operations.py`, `operation_tools.py` | tools de operación declaradas en la KB |
| `event_tools.py`, `entity.py` | tools de evento y de entidad |
| `primitives.py` | `records.*`, `subject_events.*`, `messages.send` (Twilio) |
| `apis.py` | `ApiTool`, `ApiSpec`, `ApisPort`, `api_tool` — tools de API externa |
| `idempotency.py` | idempotencia por reserva (`idempotency_key`, 03 I7/D15) |
| `kb_operations.py`, `check_kb.py` | operaciones de KB y `check-kb` |
| `tool_tests.py` | testeo desde `ToolTestDoc` |

Las tools de un turno corren en serie (`sequential`) dentro de la corrida de `decide` (06).

## Guías

- [`docs/guias/tools.md`](../../docs/guias/tools.md) — agregar una tool
- [`docs/tools-infra-y-semantica.md`](../../docs/tools-infra-y-semantica.md) — qué es primitiva del runtime y qué es tool del cliente

## Tests

`make test M=runtime/tools`
