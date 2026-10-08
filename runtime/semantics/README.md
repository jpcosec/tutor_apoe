# semantics (spec 15)

Spec 15: la ontología del runtime; coordina KB, entidades, tools y el texto que ven los agentes.

Contrato: [`specs/spec-15-ontologia-runtime.md`](../../specs/spec-15-ontologia-runtime.md)

| Si buscás | Andá a |
|---|---|
| qué hace y qué queda afuera | spec §1, §2 |
| cómo se declara una entidad | spec §4 |
| lo que no se negocia | spec §5 |
| el contrato exportado | spec §7 · [`src/semantics/__init__.py`](src/semantics/__init__.py) |
| cómo se prueba | spec §8 · [`tests/`](tests/) |
| qué NO decidir por tu cuenta | spec §12 |

## Cómo está armado

| Archivo | Qué hace |
|---|---|
| `ontology.py` | `Ontology`, `Resolved`, `UnknownRef`, `TurnSummaryLike` — `resolve`, `citable` |
| `entities.py` | `entity_type`, `ENTITY_TAG` — entidades desde `EntityDoc` |
| `views.py` | las vistas de sldb: tablas, nunca `repr` |

Todo lo que entra a un prompt pasa por acá: la huella del módulo incluye los contratos de sus vistas.

## Guías

- [`docs/arquitectura-ontologia-kb-cliente-tools-agentes.md`](../../docs/arquitectura-ontologia-kb-cliente-tools-agentes.md) — cómo encajan ontología, KB, tools y agentes
- [`docs/tools-infra-y-semantica.md`](../../docs/tools-infra-y-semantica.md) — qué es primitiva y qué es semántica
- [`specs/spec-13-ontologia.md`](../../specs/spec-13-ontologia.md) — la raíz común (`ontology`)

## Tests

`make test M=runtime/semantics`
