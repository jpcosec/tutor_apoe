# context (spec 14)

Spec 14: el contexto del flujo agéntico, su ruteador por rol y su proyección determinista.

Contrato: [`specs/spec-14-contexto.md`](../../specs/spec-14-contexto.md)

| Si buscás | Andá a |
|---|---|
| qué hace y qué queda afuera | spec §1, §2 |
| cómo se declara el contexto | spec §4 |
| lo que no se negocia | spec §5 |
| el contrato exportado | spec §7 · [`src/context/__init__.py`](src/context/__init__.py) |
| cómo se prueba | spec §8 · [`tests/`](tests/) |
| qué NO decidir por tu cuenta | spec §12 |

## Cómo está armado

| Archivo | Qué hace |
|---|---|
| `model.py` | `Context`: perfil, traza, átomos activos por rol, ledger, transcripciones |
| `router.py` | `ContextRouter`, `Candidate`, `RoleRoute`, `RouteContextConfig` — ruteo por porción de la KB |
| `selector.py` | `ContextSelection`, `LlmSelector` (selección asistida por modelo) |
| `projection.py` | `Projection`, `project` — proyección determinista por rol |
| `atoms.py` | `AtomEntry`, `LedgerEvent`, `replay_active` |
| `episodes.py` | `AgentRun`, `StepVisit`, `agent_run`, `move_to`, `close_visits` |
| `store.py` | `ContextStore`, `InMemoryContextStore`, `load`, `save` |
| `summary.py` | `TurnSummary` — el resumen por turno |

El panel `/api/context/{session}` (07) muestra este contexto.

## Guías

- [`docs/sujeto-conversacion-turno.md`](../../docs/sujeto-conversacion-turno.md) — sujeto, conversación, turno y episodios
- [`docs/arquitectura-ontologia-kb-cliente-tools-agentes.md`](../../docs/arquitectura-ontologia-kb-cliente-tools-agentes.md) — qué entra al prompt y de dónde

## Tests

`make test M=runtime/context`
