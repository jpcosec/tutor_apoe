# llm (spec 04)

Módulo 04: el modelo de lenguaje sobre Pydantic AI. Su interfaz tiene tres audiencias; cada bloque
de `__all__` dice cuál es la suya.

Contrato: [`specs/spec-04-llm.md`](../../specs/spec-04-llm.md)

| Si buscás | Andá a |
|---|---|
| qué hace y qué queda afuera | spec §1, §2 |
| qué absorbe Pydantic AI y qué queda acá | spec §3 |
| configuración (`LLM_PROVIDER`, `LLM_MODEL`, región) | spec §4 |
| lo que no se negocia | spec §5 |
| el contrato exportado | spec §7 · [`src/llm/__init__.py`](src/llm/__init__.py) |
| cómo se prueba | spec §8 · [`tests/`](tests/) |

## Cómo está armado

| Archivo | Qué hace |
|---|---|
| `factory.py` | `make_model` sobre Pydantic AI (Bedrock, OpenAI, OpenRouter) |
| `settings.py` | lectura de `LLM_PROVIDER` / `LLM_MODEL` / región del entorno |
| `capabilities.py` | `Capabilities`, `capabilities_of` |
| `conformance.py` | `run_conformance`, `ConformanceReport`, `report_path`, `report_problem` |
| `errors.py` | clasificación de errores (`LlmAuthError`, `LlmOutputInvalid`, `InternalFault`, …) |
| `outcome.py` | la corrida como resultado tipado (incluye `error_class`) |
| `scripted.py` | `ScriptedModel` para pruebas |
| `conformance_reports/` | informes de conformidad por par proveedor/modelo |

## Guías

- [`docs/guias/providers.md`](../../docs/guias/providers.md) — agregar un provider de LLM
- [`docs/guias/runtime.md`](../../docs/guias/runtime.md) — variables de entorno del modelo

## Tests

`make test M=runtime/llm`
