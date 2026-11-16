# El compilador: átomos nuevos a pedido, con procedencia, sin contaminar al tutor

`tutor.compiler` produce átomos candidatos a partir de las fuentes ingeridas. Nada de lo que
propone llega al tutor hasta que una persona lo aprueba.

## Flujo: pedir → proponer → revisar → aprobar

```
tutor compile ingest sources/Arnon.pdf --kb kbs/apos --title "Arnon et al. (2014) APOS Theory"
tutor compile run "el ciclo ACE y cómo se diseñan sus actividades" --kb kbs/apos --max 5 [--dry-run]
tutor compile list --kb kbs/apos [--status proposed|rejected|approved|all]
tutor compile show atom-… --kb kbs/apos
tutor compile approve atom-… [atom-…] --kb kbs/apos
tutor compile reject atom-… --why "redundante" --kb kbs/apos
tutor compile gaps --questions benchmarks/apos_questions.yaml --kb kbs/apos
```

Las mismas operaciones por MCP (`tutor-mcp`): `ingest_pdf`, `compile_atoms(kb_id, request,
max_atoms, dry_run)`, `list_proposed(kb_id, status)`, `approve_atom`, `reject_atom`, `find_gaps(kb_id,
questions)`.

1. **Pedir.** `request` es un tema («la tematización de un esquema») o una pregunta de estudiante
   que el tutor no cubre bien. `gaps` ayuda a encontrarlas: para cada pregunta mide el noul máximo
   (Jev) de los 30 átomos más cercanos de la mesa; bajo 0.5 es un vacío.
2. **Proponer.** Un `pydantic_ai.Agent` (modelo de `TUTOR_MODEL`, por defecto DeepSeek vía
   OpenRouter) con `output_type=list[AtomProposal]` y tools de lectura: `search_chunks` (índice
   propio de los `SourceChunk`, embedding hash cacheado en `<kb>/.cache/`), `get_chunk`,
   `search_atoms` (para no duplicar), `list_branches`, `get_atom`. Ve tres átomos existentes como
   muestra de voz y la lista de ramas para elegir `parent`.
3. **Revisar (en código).** Cada propuesta se rechaza, con razones, si:
   - `parent` no existe o no es una rama (`BranchNode`);
   - `provenance.chunk_ids` cita fragmentos que no están en la KB;
   - duplica un átomo existente (coseno hash de título+respuesta > 0.9) o repite un id de la tanda;
   - ya existe un `KnowledgeAtom` con ese id.

   Además el esquema exige título ≤ 90 caracteres, respuesta ≤ 80 palabras (una sola afirmación),
   cita textual ≤ 60 palabras y tags `namespace:valor`. Si hay `TYPESAFE_API_KEY`, un Noul de Jev
   («¿la respuesta está respaldada por el fragmento citado?») marca `grounded` (true/false; `null`
   sin Jev). `similar_to` lista los átomos existentes con similitud ≥ 0.5.
4. **Aprobar.** Los aceptados se escriben como `ProposedAtom` en `proposed/<id>.md` con `status`,
   `request`, `created_by`, `rationale`, `chunk_ids`, `similar_to`, `grounded`. `approve` borra ese
   archivo y escribe un `KnowledgeAtom` con el mismo id en `knowledge/` con su arista `child_of`
   (vía `upsert_atom`): desde ahí entra al índice y a la mesa. `reject` lo deja en `proposed/` con
   `status: rejected` y el motivo.

## Por qué el tutor no ve los propuestos

`projection-tutor` nombra `KnowledgeAtom` y `BranchNode` (con subclases) y `kb.yaml` indexa solo
`KnowledgeAtom`. `ProposedAtom` es un modelo aparte (familia `proposed`, tag `type.proposal.atom`),
no una subclase: `kb.in_projection("tutor")` lo filtra y el índice no lo embebe, así que
`tutor.agent.build_context` nunca lo trae y `explore`/`show_atom` tampoco. No lleva `child_of`:
`parent` es solo el destino que tendrá al aprobarse. `tests/tutor/test_compiler.py` lo verifica.

## Costo

- Ingesta e índice de fragmentos: sin red (pypdf + `HashEmbedder`). El PDF de Arnon (259 páginas)
  son 623 fragmentos de ~1200 caracteres; el índice se cachea por hash de contenido.
- `compile`: una conversación con el LLM (hasta 16 peticiones con tools, 4096 tokens de salida
  como tope). Con DeepSeek V4.1 Flash por OpenRouter, un pedido de 5 átomos cuesta del orden de
  30–60k tokens de entrada (los fragmentos leídos) y 2–3k de salida; `usage` viene en el resultado.
- `grounded` y `gaps`: un Noul de Jev por propuesta aceptada, o por átomo del pool (≤ 30) por
  pregunta. Sin `TYPESAFE_API_KEY` se omiten sin error.
