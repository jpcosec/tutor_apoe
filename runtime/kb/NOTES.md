# Registro de casos que el spec 01 no cubre (§12)

Cada entrada: regla o sección, dónde aparece en la KB de control, qué se hizo y
qué opciones ve el dueño. Nada de esto se resolvió con una convención silenciosa:
está aquí y en el código apunta a este archivo.

| # | Regla / sección | Dónde aparece | Qué hace el módulo hoy | Opciones |
|---|---|---|---|---|
| N8 | §6.3 y §7.1 | — | `projection()`, `in_projection()`, `rank()`, `refresh_index()`, `audit_index()` implementados sobre el `Corpus` de sldb (sin pron), con el embedder inyectado (decisiones E1–E6). `retrack(root, refs)` implementado como función (no método: corre antes de que la KB abra), sobre `sldb.api` (`check_store`, `untrack_document`, `track_document_file`, `update_store_indexes`); CLI `kb retrack`; 09 lo llama sobre la copia del release antes de abrirla | cerrada |

Resueltos en el spec (2026-09-28): N3 (parent ausente es None, §4.3), N4 (carga masiva por
`sldb.api`, §3.0), N5 (`pron.` es built-in, V1), N6 (roles `type.knowledge.style` y
`type.knowledge.strategy`, §6.4 y V12) y N7 (conteos medidos, §10.2).

Resueltos en el spec y en la KB (2026-09-27), ya sin arreglos en el código:

- **N1** (nombres de `RelationDoc` con `:`): 13 §4.0 norma identificadores, tags y
  referencias; los `RelationDoc` se llaman `<tipo>--<origen>--<destino>` con
  nombres de documento, y 01 V13 lo valida. La KB se regeneró con esos nombres.
- **N2** (contador de `MoveDoc`): la KB v1 ya no registra `MoveDoc` (historial de
  pron) y el store queda en PASS; C1 y V1 vuelven a ser estrictos.

Correcciones hechas en la KB de control al implementar (rama `rebuild/kb-cobranza`
de ChatbotsKnowledgeBases): `pythonpath: ..` en `kb.yaml`, `parent` opcional en
`TagNamespaceDoc`, y el `id` de `rule-cobranza-primer-envio-propio` (lo detectó V2).
