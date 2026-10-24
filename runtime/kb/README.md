# kb (spec 01)

Acceso de solo lectura a una KB sldb: abrir, validar (V0–V13), consultar por
modelo, tag, familia y relación, renderizar y materializar. No escribe en la KB,
no usa red ni modelos de lenguaje.

```python
from kb import KnowledgeBase

kb = KnowledgeBase.open(Path("kbs/knowledge_antonia-cobranza"))   # KnowledgeBaseInvalid si no valida
kb.by_model("ToolAtom")               # incluye ExternalApiToolAtom, DataToolAtom, ReadToolAtom
kb.by_tag("type.knowledge")           # el tag y sus descendientes
kb.relations("transitions_to")        # Relation(source_ref, target_ref, condition, doc)
kb.materialize()                      # un Markdown determinista de lo elegible
kb.stats()
```

```bash
kb validate <root>          # 0 si válida; si no, una línea por error: regla  origen  doc  ruta  mensaje
kb query <root> --model ToolAtom [--exact] [--eligible]
kb show | materialize | stats <root> [--lenient]
```

## Cómo está armado

| Carpeta | Qué hace |
|---|---|
| `declaration/` | `kb.yaml` (contrato `kb_version: 1`) |
| `loading/sldb_gateway.py` | **el único archivo que importa sldb** (solo `sldb.api` más las excepciones listadas en `tests/test_sldb_boundary.py`) |
| `loading/` | índice del store, carga de documentos, C1 |
| `model/` | `Document` (deriva de `OntologyObject`), `ModelInfo`, `Relation`, `RelationTypeInfo`, `KbStats` |
| `validation/rules/` | una función por regla V1–V13; `validator.py` las corre todas |
| `graph/`, `rendering/` | relaciones por tipo; render de sldb y materialización |
| `payload.py` | lectura tipada de valores dinámicos |
| `kb_base/` | `CategoryDoc`, `ReferenceConversation`, `ToolTest` (opcionales, D3/D7/D12) |

## Pruebas

- Una KB negativa por regla, construida con las escrituras de sldb
  (`tests/fixtures/make_fixture.py`, modelos en `tests/fixtures/minimal_models`).
- `test_contract_sldb.py` fija las conductas de sldb de las que depende el módulo.
- Las pruebas contra una KB real de cliente (materialización, golden, retrack) viven en
  `clients/cobranza/tests/` (`KBS_ROOT`, por defecto `../kbs`): el módulo no depende de
  ningún cliente (R10).

Casos que el spec no cubre y cómo se resolvieron: `NOTES.md`.
