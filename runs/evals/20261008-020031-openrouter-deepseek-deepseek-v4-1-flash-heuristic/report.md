# Eval del tutor · openrouter:deepseek/deepseek-v4.1-flash · selector heuristic

KB `apos` · k=8 · 20 preguntas · 2026-10-08T02:00:31 · 477.1 s · groundedness: ok

## Resumen

| métrica | valor |
|---|---|
| preguntas (ok/errores) | 20/0 |
| hit@1 | 0.75 |
| hit@8 | 0.85 |
| MRR | 0.79 |
| tag_hit@8 | 0.90 |
| max noul medio (Jev) | – |
| max noul mínimo (Jev) | – |
| citas por respuesta | 4.05 |
| citas válidas (tasa) | 1.00 |
| citas en mesa (tasa) | 1.00 |
| ids inventados (total) | 0 |
| citas fuera de mesa (total) | 0 |
| coverage de expected | 0.85 |
| respuestas sin citas | 0 |
| groundedness | ok |
| oraciones respaldadas | 82/90 |
| fracción respaldada | 0.91 |
| chars por respuesta | 989.65 |
| latencia media (ms) | 5263.39 |
| latencia máx (ms) | 8499.20 |
| tokens in/out (total) | 80841/7771 |
| costo USD (total) | – |

## Por pregunta

| id | hit@1 | hit@8 | rr | max noul | citas | válidas | en mesa | coverage | respaldadas | ms | tok in/out |
|---|---|---|---|---|---|---|---|---|---|---|---|
| q01-accion | 1 | 1 | 1.00 | – | 3 | 3/3 | 3/3 | 1.00 | 4/4 | 4466 | 2146/305 |
| q02-proceso | 0 | 0 | 0.00 | – | 4 | 4/4 | 4/4 | 1.00 | 5/5 | 5998 | 8432/525 |
| q03-objeto | 1 | 1 | 1.00 | – | 4 | 4/4 | 4/4 | 0.50 | 4/4 | 1830 | 2101/278 |
| q04-esquema | 1 | 1 | 1.00 | – | 5 | 5/5 | 5/5 | 0.67 | 5/5 | 2862 | 2019/324 |
| q05-encapsulacion | 1 | 1 | 1.00 | – | 5 | 5/5 | 5/5 | 1.00 | 5/5 | 5685 | 2080/396 |
| q06-desencapsulacion | 1 | 1 | 1.00 | – | 3 | 3/3 | 3/3 | 1.00 | 3/4 | 6047 | 2171/317 |
| q07-totalidad | 0 | 1 | 0.50 | – | 4 | 4/4 | 4/4 | 1.00 | 4/4 | 6739 | 4606/505 |
| q08-interiorizacion | 1 | 1 | 1.00 | – | 5 | 5/5 | 5/5 | 1.00 | 5/5 | 4400 | 1996/309 |
| q09-coordinacion | 1 | 1 | 1.00 | – | 3 | 3/3 | 3/3 | 1.00 | 3/5 | 4258 | 2130/269 |
| q10-reversion | 1 | 1 | 1.00 | – | 2 | 2/2 | 2/2 | 1.00 | 4/4 | 6852 | 8017/521 |
| q11-tematizacion | 1 | 1 | 1.00 | – | 5 | 5/5 | 5/5 | 1.00 | 4/5 | 7552 | 7519/482 |
| q12-descomposicion-genetica | 1 | 1 | 1.00 | – | 6 | 6/6 | 6/6 | 1.00 | 7/7 | 4681 | 2155/341 |
| q13-ciclo-ace | 1 | 1 | 1.00 | – | 4 | 4/4 | 4/4 | 1.00 | 2/4 | 3754 | 2038/297 |
| q14-isetl | 0 | 1 | 0.25 | – | 4 | 4/4 | 4/4 | 0.50 | 3/4 | 5138 | 2038/388 |
| q15-piaget-abstraccion-reflexiva | 1 | 1 | 1.00 | – | 5 | 5/5 | 5/5 | 1.00 | 5/5 | 3653 | 2059/283 |
| q16-rumec | 1 | 1 | 1.00 | – | 2 | 2/2 | 2/2 | 1.00 | 3/3 | 5981 | 7233/375 |
| q17-funciones | 0 | 0 | 0.00 | – | 4 | 4/4 | 4/4 | 0.00 | 4/4 | 8499 | 7568/582 |
| q18-grupos | 1 | 1 | 1.00 | – | 4 | 4/4 | 4/4 | 1.00 | 4/4 | 4498 | 2046/352 |
| q19-escuela-elemental | 0 | 0 | 0.00 | – | 5 | 5/5 | 5/5 | 0.67 | 4/4 | 7256 | 7898/522 |
| q20-paradigma-investigacion | 1 | 1 | 1.00 | – | 4 | 4/4 | 4/4 | 0.67 | 4/5 | 5117 | 4589/400 |

## Peores preguntas

- **q17-funciones** (1.0): ningún expected en la mesa; no cita atom-function-genetic-decomposition-begins-with-actions-on-elements
- **q14-isetl** (1.5): primer expected en posición 4; no cita atom-isetl-syntax-stays-close-to-standard-mathematical-notation; 1 oración(es) no respaldada(s)
- **q19-escuela-elemental** (1.667): ningún expected en la mesa; no cita atom-imagination-plays-a-substantial-role-in-young-childrens-interiorization

## Oraciones no respaldadas por el átomo citado

- **q06-desencapsulacion** (noul 0.28, cita atom-encapsulation-treats-a-process-as-a-static-entity): Recordemos que la encapsulación convierte un proceso en objeto al verlo como totalidad transformable [atom-encapsulation-treats-a-process-as-a-static-entity]; la desencapsulación es su movimiento inverso.
- **q09-coordinacion** (noul 0.38, cita atom-reversal-is-central-for-inverses-and-related-constructions): Se distingue de la reversión: esta última reconstruye un proceso en sentido inverso, por ejemplo para la función inversa o la antiderivación [atom-reversal-is-central-for-inverses-and-related-constructions]; la coordinación, en cambio, articula procesos entre sí.
- **q09-coordinacion** (noul 0.26, cita atom-coordination-combines-processes-to-build-new-objects-or-processes): Ejemplo citado: la composición de funciones [atom-coordination-combines-processes-to-build-new-objects-or-processes].
- **q11-tematizacion** (noul 0.21, cita atom-de-encapsulation-recovers-the-underlying-process-of-an-object): Así, el esquema pasa de organizador global a entidad sobre la que se opera, análogamente a encapsular un proceso en objeto [atom-de-encapsulation-recovers-the-underlying-process-of-an-object].
- **q13-ciclo-ace** (noul 0.07, cita atom-ace-cycle-is-the-main-apos-instructional-pattern): **A – Actividades**: inician las construcciones mentales del estudiante [atom-ace-cycle-is-the-main-apos-instructional-pattern].
- **q13-ciclo-ace** (noul 0.16, cita atom-ace-cycle-is-the-main-apos-instructional-pattern): **C – Discusión en clase**: continúa y profundiza esas construcciones [atom-ace-cycle-is-the-main-apos-instructional-pattern].
- **q14-isetl** (noul 0.32, cita atom-classroom-discussion-helps-students-reflect-on-activity-work): Al ejecutar y reflexionar, apoya la construcción de estructuras mentales (como Proceso) que luego se discuten en clase [atom-classroom-discussion-helps-students-reflect-on-activity-work].
- **q20-paradigma-investigacion** (noul 0.39, cita atom-apos-book-presents-framework-for-research-and-curriculum-development, atom-theoretical-models-increase-reliability-of-data-analysis): Como metodología, ofrece un marco para investigación y desarrollo curricular [atom-apos-book-presents-framework-for-research-and-curriculum-development]; la descomposición genética se usa como modelo teórico que aumenta la confiabilidad del análisis [atom-theoretical-models-increase-reliability-of-data-analysis].
