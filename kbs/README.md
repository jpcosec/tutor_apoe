# kbs — bases de conocimiento sldb del tutor

Una KB por carpeta, abrible con `kb.KnowledgeBase.open(root, embedder)` (runtime/kb). El
esquema compartido vive en `kb_models/` (pythonpath `kbs/`).

```
kbs/
├── kb_models/          esquema: KnowledgeAtom, SourceAtom, BranchNode, AgentDoc, TagNamespaceDoc
└── apos/               la KB de la teoría APOS (generada; .md versionados, .sldb/ derivado)
    ├── kb.yaml         contrato kb_version 1: modelos, categorías, política de índice (embedder)
    ├── tag-namespaces.yaml
    ├── knowledge/**    89 KnowledgeAtom, misma ruta relativa e id que en desk/atoms/apos/
    ├── sources/**      5 SourceAtom (átomos sobre el libro fuente)
    ├── taxonomy/       59 BranchNode: 47 de desk/atoms/branches + 12 ramas intermedias inferidas
    ├── relations/      151 RelationDoc `child_of--<hijo>--<padre>` (uno por parent_id)
    ├── kgdb/relation_types/child_of.md
    ├── categories/     6 TagNamespaceDoc (agent, domain, layer, node, system, topic)
    ├── agent/agent-tutor-apos.md      rol `tutor`: persona e instrucciones del pack apos
    ├── projections/projection-tutor.md ProjectionDoc: KnowledgeAtom + BranchNode + child_of
    ├── sldb/relation_types/           tipos estructurales que escribe sldb (init_relations)
    └── .sldb/          DERIVADO, fuera de git: store, índices, aristas, caché de vectores
```

## Regenerar

```bash
export PYTHONPATH=runtime/ontology/src:runtime/cognitive/src:runtime/kb/src:runtime/embeddings/src:kbs:src
python -m tutor.kb_build --atoms desk/atoms --out kbs/apos          # ~40 s; idempotente
python -c "from kb.cli import main; main()" validate kbs/apos         # 0 si válida
python -m pytest tests/tutor -q
```

`kb_build` borra lo generado la vez anterior (documentos y `.sldb/`), reescribe los `.md`
con la API de sldb, arma el store, valida con `kb` (V0–V13) y refresca el índice de
embeddings. Dos corridas producen bytes idénticos. `tutor.world.open_kb()` lo invoca solo
si falta `.sldb/` (p. ej. en un contenedor recién clonado).

## Qué es fuente y qué es derivado

- **Fuente**: `desk/atoms/**` (los átomos editados por personas) y `apps/kb_agent/packs/apos/`
  (persona y política del rol).
- **Generado y versionado**: los `.md` de `kbs/apos/`, `kb.yaml`, `tag-namespaces.yaml`.
  Se versionan para que cualquier consumidor los lea sin sldb y para revisar diffs.
- **Derivado, ignorado por git** (`.gitignore`: `kbs/*/.sldb/`): el store `.sldb/`
  (`core/store_index.yaml` lleva rutas absolutas de la máquina), `runtime/` (journal,
  aristas, locks) y los vectores en `.sldb/runtime/cache/corpus/docs.*.json`.

## Embedder

La KB declara `index.embedder_id: hash:char-ngram-256` (`tutor.embedding.HashEmbedder`:
n-gramas de caracteres hasheados a 256 dims, determinista, sin red). `kb` exige que el
embedder con que se abre tenga ese mismo id; para usar fastembed hay que regenerar con
`python -m tutor.kb_build --embedder fastembed[:modelo]` (o `TUTOR_EMBEDDER=fastembed`).
