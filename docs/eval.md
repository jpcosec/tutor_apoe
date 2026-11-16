# Evaluar al tutor y a la KB (`tutor eval`)

`src/tutor/eval.py` mide dos cosas distintas: **cómo razona el agente** (qué átomos pone en la mesa,
qué cita, si lo que afirma está respaldado) y **cómo está la KB** (átomos con problemas o que nunca
se usan). Se engancha al CLI (`tutor eval …`) y al MCP (`eval_run`, `explain_turn`, `eval_atoms`)
sin tocar `cli.py` ni `mcp_server.py`.

```bash
tutor eval run                                   # DeepSeek + Jev (según .env.defaults), 20 preguntas, ~1.5–3 min
tutor eval run --selector heuristic              # mismo modelo, mesa por embedding+heurística del router
tutor eval run --model test --limit 3            # sin red (respuesta guionada), para probar el pipeline
tutor eval run --questions benchmarks/apos_questions_hard.yaml
tutor eval report runs/evals/<dir>               # reimprime el resumen (--md: el report.md completo)
tutor eval compare runs/evals/<A> runs/evals/<B> # A vs B con delta, y por pregunta
tutor eval turn "¿Qué es la encapsulación?"      # UN turno explicado (acepta un id del YAML: q05-encapsulacion)
tutor eval atoms [--evals runs/evals] [--json out.json]
```

Cada corrida deja `runs/evals/<timestamp>-<modelo>-<selector>/results.json` (todo: mesa, `reasoning_log`,
respuesta, métricas por pregunta) y `report.md` (tablas).

## Qué mide cada métrica (por pregunta y promedio)

**Retrieval** — ¿entraron a la mesa los átomos que el YAML declara como `expected_atom_ids`?

| métrica | significado |
|---|---|
| `hit@1` | el primer átomo de la mesa es uno de los expected |
| `hit@k` | algún expected está en la mesa (k = tamaño de la mesa, 8 por defecto) |
| `MRR` | 1/posición del primer expected (0 si ninguno) |
| `tag_hit@k` | algún átomo de la mesa lleva un `expected_tags` |
| `max noul` / `min noul` | solo con selector Jev: el noul («¿este átomo aporta evidencia?») más alto y más bajo entre los átomos que Jev eligió. Un **max noul bajo (< 0.5) es la señal de que la KB no cubre la pregunta**, aunque la mesa esté llena |

Las fórmulas son las de `benchmarks/run.py` (`evaluate`). Preguntas con `expected_atom_ids: []` no
puntúan en retrieval (`scored: false`), sirven para mirar el noul y las citas.

**Citas** — los ids `[atom-…]` que aparecen en la respuesta.

| métrica | significado |
|---|---|
| `citas por respuesta` | cuántos ids distintos cita |
| `válidas` | el id existe en la KB. Un id que no existe es un **id inventado** |
| `en mesa` | el id estaba en la mesa del turno o fue leído con `show_atom`. Citar un id válido que no vio (**fuera de mesa**) es alucinación de cita |
| `coverage` | expected citados / expected: ¿usó la evidencia que debía? |

**Groundedness (Jev)** — la respuesta se parte en oraciones; por cada oración con cita se pregunta a
Jev (TypeSafe System One, un `Noul`) si el átomo citado (título + respuesta) **afirma o implica** la
oración. Umbral 0.5. Se reporta `respaldadas m/n`, la fracción y la lista de oraciones no respaldadas
(con su noul). Patrón tomado del cookbook `citation_check` de TypeSafe, simplificado a un Noul por
(oración, átomo). Sin `TYPESAFE_API_KEY` o sin `typesafe_sdk`: `skipped`. Una oración que cita varios
átomos se da por respaldada si alguno la respalda.

**Respuesta** — chars, nº de citas, latencia del turno (incluye selector y herramientas), tokens
in/out, costo si el proveedor lo informa (OpenRouter vía `llm` no lo informa: queda `–`).

**Peores preguntas** — puntaje `rr + coverage + fracción respaldada − 1 si inventó o citó fuera de
mesa`; un error del proveedor va primero. Al lado, por qué (qué expected no citó, cuántas oraciones
sin respaldo, max noul bajo…).

## Cómo leer un `report.md`

1. Cabecera: modelo, selector efectivo (`jev` o `heuristic`; `auto` cae a heurística sin key),
   k, duración, si la groundedness corrió.
2. **Resumen**: si `hit@k` es alto pero `coverage` bajo, el problema es el agente (tenía la evidencia
   y no la citó). Si `hit@k` es bajo, el problema es retrieval/KB. Si `citas fuera de mesa` o
   `ids inventados` > 0, el modelo no respeta la política de citas. Si `fracción respaldada` < 0.9,
   mira la sección de oraciones no respaldadas: suelen ser generalizaciones o ejemplos que el átomo
   no contiene.
3. **Por pregunta**: una fila por pregunta; `respaldadas 3/4` = 4 oraciones con cita, 3 respaldadas.
4. `tutor eval turn <id>` para abrir una pregunta: mesa con `E` (expected) y `C` (citado) por átomo,
   su score (noul con Jev), lo que no entró a la mesa y la verificación oración por oración.

`tutor eval compare A B` pone los dos resúmenes lado a lado con `B−A` y, por pregunta, `hit@k`,
`rr`, `coverage`, `respaldada` y latencia como `A/B`.

## `tutor eval atoms`

Sin LLM. Para la KB: átomos sin `provenance`, respuestas < 80 o > 1200 chars, títulos casi
duplicados (Jaccard de palabras del título normalizado ≥ 0.9, o coseno del embedding hash del
título ≥ 0.9), tags cuyo namespace no está declarado en `tag-namespaces.yaml`, ramas sin ningún
átomo debajo, átomos sin `child_of` (huérfanos) o con `parent` inexistente. Con corridas en
`runs/evals/`: cuántas veces entró cada átomo a una mesa y fue citado → **nunca usados** (candidatos a
revisar título/tags o a fusionar) y los **más usados**.

## Costo y tiempo aproximados (20 preguntas, k = 8)

- LLM: ~1.6k tokens de entrada y ~300 de salida por pregunta con DeepSeek V4.1 Flash por OpenRouter
  (~35k in / ~6k out por corrida): centavos de dólar. OpenRouter reserva `TUTOR_MAX_TOKENS` (1500)
  por petición contra el crédito disponible; con poco saldo devuelve 402 `in_flight_budget_exhausted`
  y `eval run` espera el `Retry-After` y reintenta (2 veces por pregunta).
- Jev: selector ≈ 30 Nouls por pregunta + groundedness ≈ 4–6 Nouls por pregunta (~700 llamadas por
  corrida), en paralelo (8 hilos).
- Tiempo: 90–180 s por corrida; ~4 s por turno de los que ~1 s es el selector.
- `--model test` + `FakeJevClient` (en tests): 0 red, < 1 s.
