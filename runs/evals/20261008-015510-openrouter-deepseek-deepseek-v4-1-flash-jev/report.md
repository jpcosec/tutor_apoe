# Eval del tutor · openrouter:deepseek/deepseek-v4.1-flash · selector jev

KB `apos` · k=8 · 20 preguntas · 2026-10-08T01:55:10 · 226.6 s · groundedness: ok

## Resumen

| métrica | valor |
|---|---|
| preguntas (ok/errores) | 20/0 |
| hit@1 | 0.90 |
| hit@8 | 1.00 |
| MRR | 0.95 |
| tag_hit@8 | 1.00 |
| max noul medio (Jev) | 0.85 |
| max noul mínimo (Jev) | 0.69 |
| citas por respuesta | 4.00 |
| citas válidas (tasa) | 1.00 |
| citas en mesa (tasa) | 1.00 |
| ids inventados (total) | 0 |
| citas fuera de mesa (total) | 0 |
| coverage de expected | 0.97 |
| respuestas sin citas | 0 |
| groundedness | ok |
| oraciones respaldadas | 85/89 |
| fracción respaldada | 0.96 |
| chars por respuesta | 987.25 |
| latencia media (ms) | 4669.68 |
| latencia máx (ms) | 7832.60 |
| tokens in/out (total) | 45527/6702 |
| costo USD (total) | – |

## Por pregunta

| id | hit@1 | hit@8 | rr | max noul | citas | válidas | en mesa | coverage | respaldadas | ms | tok in/out |
|---|---|---|---|---|---|---|---|---|---|---|---|
| q01-accion | 1 | 1 | 1.00 | 0.89 | 5 | 5/5 | 5/5 | 1.00 | 5/5 | 5671 | 1574/289 |
| q02-proceso | 1 | 1 | 1.00 | 0.94 | 4 | 4/4 | 4/4 | 1.00 | 4/4 | 4131 | 1571/302 |
| q03-objeto | 0 | 1 | 0.50 | 0.85 | 3 | 3/3 | 3/3 | 0.50 | 4/4 | 3908 | 1603/293 |
| q04-esquema | 1 | 1 | 1.00 | 0.95 | 6 | 6/6 | 6/6 | 1.00 | 5/5 | 7411 | 5991/534 |
| q05-encapsulacion | 1 | 1 | 1.00 | 0.69 | 3 | 3/3 | 3/3 | 1.00 | 3/4 | 3103 | 1295/279 |
| q06-desencapsulacion | 1 | 1 | 1.00 | 0.92 | 4 | 4/4 | 4/4 | 1.00 | 4/4 | 4830 | 1872/397 |
| q07-totalidad | 1 | 1 | 1.00 | 0.77 | 4 | 4/4 | 4/4 | 1.00 | 5/5 | 4270 | 5790/421 |
| q08-interiorizacion | 1 | 1 | 1.00 | 0.94 | 4 | 4/4 | 4/4 | 1.00 | 4/4 | 5600 | 1414/281 |
| q09-coordinacion | 1 | 1 | 1.00 | 0.93 | 3 | 3/3 | 3/3 | 1.00 | 3/4 | 3287 | 1908/248 |
| q10-reversion | 1 | 1 | 1.00 | 0.75 | 3 | 3/3 | 3/3 | 1.00 | 5/5 | 5243 | 3277/471 |
| q11-tematizacion | 1 | 1 | 1.00 | 0.94 | 4 | 4/4 | 4/4 | 1.00 | 4/5 | 4869 | 1582/371 |
| q12-descomposicion-genetica | 1 | 1 | 1.00 | 0.77 | 5 | 5/5 | 5/5 | 1.00 | 5/5 | 4097 | 1600/305 |
| q13-ciclo-ace | 1 | 1 | 1.00 | 0.76 | 3 | 3/3 | 3/3 | 1.00 | 3/3 | 5160 | 1274/264 |
| q14-isetl | 1 | 1 | 1.00 | 0.85 | 5 | 5/5 | 5/5 | 1.00 | 5/5 | 3241 | 1595/264 |
| q15-piaget-abstraccion-reflexiva | 1 | 1 | 1.00 | 0.85 | 5 | 5/5 | 5/5 | 1.00 | 5/5 | 7833 | 5700/609 |
| q16-rumec | 1 | 1 | 1.00 | 0.84 | 2 | 2/2 | 2/2 | 1.00 | 4/4 | 3686 | 1414/225 |
| q17-funciones | 0 | 1 | 0.50 | 0.89 | 4 | 4/4 | 4/4 | 1.00 | 4/5 | 3823 | 1597/254 |
| q18-grupos | 1 | 1 | 1.00 | 0.81 | 4 | 4/4 | 4/4 | 1.00 | 4/4 | 3855 | 1444/327 |
| q19-escuela-elemental | 1 | 1 | 1.00 | 0.82 | 4 | 4/4 | 4/4 | 1.00 | 4/4 | 5338 | 1464/322 |
| q20-paradigma-investigacion | 1 | 1 | 1.00 | 0.91 | 5 | 5/5 | 5/5 | 1.00 | 5/5 | 4036 | 1562/246 |

## Peores preguntas

- **q03-objeto** (2.0): primer expected en posición 2; no cita atom-object-is-a-core-mental-structure-in-apos
- **q17-funciones** (2.3): primer expected en posición 2; 1 oración(es) no respaldada(s)
- **q05-encapsulacion** (2.75): 1 oración(es) no respaldada(s)

## Oraciones no respaldadas por el átomo citado

- **q05-encapsulacion** (noul 0.01, cita atom-encapsulation-is-reported-as-one-of-the-most-difficult-mechanisms): El libro lo ilustra con ejemplos sobre la media y funciones de dos variables [atom-encapsulation-is-reported-as-one-of-the-most-difficult-mechanisms].
- **q09-coordinacion** (noul 0.24, cita atom-coordination-combines-processes-to-build-new-objects-or-processes): Ejemplo típico del libro: la composición de funciones [atom-coordination-combines-processes-to-build-new-objects-or-processes].
- **q11-tematizacion** (noul 0.43, cita atom-encapsulation-treats-a-process-as-a-static-entity, atom-thematization-turns-a-schema-into-an-object): No es igual que encapsular: la encapsulación convierte un **proceso** en objeto [atom-encapsulation-treats-a-process-as-a-static-entity]; la tematización eleva un **esquema completo** a objeto [atom-thematization-turns-a-schema-into-an-object].
- **q17-funciones** (noul 0.24, cita atom-function-object-conception-supports-sets-operations-and-limits-of-functions): El punto de partida (Acción) precede a la interiorización hacia Proceso y encapsulación en Objeto, evidenciado al tratar funciones como elementos de conjuntos u operaciones [atom-function-object-conception-supports-sets-operations-and-limits-of-functions].
