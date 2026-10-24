# embeddings

Adaptadores de embeddings (decisiones E1–E6 de `decisiones-librerias-y-reglas.md`).
Cada adaptador cumple el puerto `Embedder` de sldb (`id() -> str`, `embed(texts) -> list[list[float]]`)
y su `id()` es el que la KB declara en `kb.index.embedder_id`, con la forma `<proveedor>:<modelo>`.
El módulo 01 **nunca** importa este paquete: lo recibe inyectado por el ensamblaje (10).

Contrato: [`specs/decisiones-librerias-y-reglas.md`](../../specs/decisiones-librerias-y-reglas.md) §5 (E1–E6)

| Si buscás | Andá a |
|---|---|
| la decisión y sus límites | decisiones §5 (E1–E6) |
| qué librerías se reemplazan y cuáles no | decisiones §1, §6 |
| cómo se declara el embedder de una KB | [`specs/spec-01-kb.md`](../../specs/spec-01-kb.md) §4 |

## Cómo está armado

| Archivo | Qué hace |
|---|---|
| `fastembed_embedder.py` | `FastEmbedEmbedder` — el adaptador fastembed |
| `registry.py` | `embedder_for`, `UnknownEmbedder` |

## Guías

- [`docs/guias/kb.md`](../../docs/guias/kb.md) — `kb.index.embedder_id` y el índice de la KB
- [`docs/guias/runtime.md`](../../docs/guias/runtime.md) — cómo lo inyecta el ensamblaje

## Tests

`make test M=runtime/embeddings`
