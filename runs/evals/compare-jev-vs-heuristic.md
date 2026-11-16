# Comparación · A = openrouter:deepseek/deepseek-v4.1-flash · jev · B = openrouter:deepseek/deepseek-v4.1-flash · heuristic

| métrica | A | B | B−A |
|---|---|---|---|
| preguntas (ok/errores) | 20/0 | 20/0 |  |
| hit@1 | 0.90 | 0.75 | -0.150 |
| hit@8 | 1.00 | 0.85 | -0.150 |
| MRR | 0.95 | 0.79 | -0.162 |
| tag_hit@8 | 1.00 | 0.90 | -0.100 |
| max noul medio (Jev) | 0.85 | – |  |
| max noul mínimo (Jev) | 0.69 | – |  |
| citas por respuesta | 4.00 | 4.05 | +0.050 |
| citas válidas (tasa) | 1.00 | 1.00 | +0.000 |
| citas en mesa (tasa) | 1.00 | 1.00 | +0.000 |
| ids inventados (total) | 0 | 0 | +0.000 |
| citas fuera de mesa (total) | 0 | 0 | +0.000 |
| coverage de expected | 0.97 | 0.85 | -0.125 |
| respuestas sin citas | 0 | 0 | +0.000 |
| groundedness | ok | ok |  |
| oraciones respaldadas | 85/89 | 82/90 |  |
| fracción respaldada | 0.96 | 0.91 | -0.044 |
| chars por respuesta | 987.25 | 989.65 | +2.400 |
| latencia media (ms) | 4669.68 | 5263.39 | +593.710 |
| latencia máx (ms) | 7832.60 | 8499.20 | +666.600 |
| tokens in/out (total) | 45527/6702 | 80841/7771 |  |
| costo USD (total) | – | – |  |

## Por pregunta (A/B)

| id | hit@k | rr | coverage | respaldada | ms |
|---|---|---|---|---|---|
| q01-accion | 1/1 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 5671.40/4466.50 |
| q02-proceso | 1/0 | 1.00/0.00 | 1.00/1.00 | 1.00/1.00 | 4131.00/5998.40 |
| q03-objeto | 1/1 | 0.50/1.00 | 0.50/0.50 | 1.00/1.00 | 3908.20/1830.40 |
| q04-esquema | 1/1 | 1.00/1.00 | 1.00/0.67 | 1.00/1.00 | 7411.00/2862.20 |
| q05-encapsulacion | 1/1 | 1.00/1.00 | 1.00/1.00 | 0.75/1.00 | 3102.90/5685.40 |
| q06-desencapsulacion | 1/1 | 1.00/1.00 | 1.00/1.00 | 1.00/0.75 | 4830.50/6047.10 |
| q07-totalidad | 1/1 | 1.00/0.50 | 1.00/1.00 | 1.00/1.00 | 4270.00/6738.70 |
| q08-interiorizacion | 1/1 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 5600.10/4400.40 |
| q09-coordinacion | 1/1 | 1.00/1.00 | 1.00/1.00 | 0.75/0.60 | 3286.90/4257.70 |
| q10-reversion | 1/1 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 5243.40/6851.90 |
| q11-tematizacion | 1/1 | 1.00/1.00 | 1.00/1.00 | 0.80/0.80 | 4869.20/7551.50 |
| q12-descomposicion-genetica | 1/1 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 4097.40/4680.70 |
| q13-ciclo-ace | 1/1 | 1.00/1.00 | 1.00/1.00 | 1.00/0.50 | 5159.80/3753.70 |
| q14-isetl | 1/1 | 1.00/0.25 | 1.00/0.50 | 1.00/0.75 | 3241.00/5138.30 |
| q15-piaget-abstraccion-reflexiva | 1/1 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 7832.60/3652.80 |
| q16-rumec | 1/1 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 3685.80/5981.00 |
| q17-funciones | 1/0 | 0.50/0.00 | 1.00/0.00 | 0.80/1.00 | 3823.40/8499.20 |
| q18-grupos | 1/1 | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 3854.90/4498.50 |
| q19-escuela-elemental | 1/0 | 1.00/0.00 | 1.00/0.67 | 1.00/1.00 | 5338.10/7256.00 |
| q20-paradigma-investigacion | 1/1 | 1.00/1.00 | 1.00/0.67 | 1.00/0.80 | 4035.90/5117.30 |

