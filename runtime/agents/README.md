# agents (spec 05)

Módulo 05: agentes declarados, instrucciones compiladas desde la KB, ejecución sobre Pydantic AI.
Su interfaz tiene tres audiencias; cada bloque de `__all__` dice cuál es la suya.

Contrato: [`specs/spec-05-agentes.md`](../../specs/spec-05-agentes.md)

| Si buscás | Andá a |
|---|---|
| qué hace y qué queda afuera | spec §1, §2 |
| declaración de agentes y sus variantes | spec §4 |
| lo que no se negocia | spec §5 |
| el contrato exportado | spec §7 · [`src/agents/__init__.py`](src/agents/__init__.py) |
| cómo se prueba | spec §8 · [`tests/`](tests/) |
| límites de implementación | spec §9 |

## Cómo está armado

| Archivo | Qué hace |
|---|---|
| `declaration.py` | `AgentDecl`, `AgentsDeclaration`, `ContextDecl`, `StaticSection`, `load_agents` |
| `compile.py` | `CompiledAgent`, `InstructionVariant`, `compile_agent`, `compile_all` |
| `prompt.py` | `Instructions`, `DYNAMIC_FIELDS`, `instructions_for`, `render_context` |
| `run.py` | `AgentRunner`, `AgentOutput`, `DecisionOutput`, `ReviewOutput`, `RunUsageView` |
| `schemas.py` | los esquemas tipados (`SCHEMAS`, `WITH_CLAIMS`, `DraftWithEvidence`) |
| `segments.py`, `capabilities.py`, `providers.py` | variantes por segmento, capacidades de Pydantic AI, `body_of` |
| `kb_tools.py` | `KB_TOOLS`, `KbReader` — tools de lectura de KB |

## Guías

- [`docs/guias/agentes.md`](../../docs/guias/agentes.md) — crear y configurar un agente
- [`docs/guias/kb.md`](../../docs/guias/kb.md) — de dónde se compilan las instrucciones
- [`docs/reemplazos-pydantic-ai-y-separacion-cliente.md`](../../docs/reemplazos-pydantic-ai-y-separacion-cliente.md) — qué se delegó a Pydantic AI

## Tests

`make test M=runtime/agents`
