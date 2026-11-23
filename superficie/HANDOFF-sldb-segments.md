# HANDOFF · Segmentos de documento en SLDB

Estado: **CUMPLIDO**. Fecha: 2026-09-29.
Consumidor: `@sldb/surface` (esta UI). Contrato de tipos: `src/core/contract.ts`.

Implementado en SLDB (rama `feat/document-segments`):

- `GET /document/segments` — commit `74285b5`, instrumentando el render con centinelas.
  Verificado: los segmentos concatenados reconstruyen el texto exacto y cada offset
  coincide, incluido `complete-systemprompt`, que hacía reventar al prototipo.
- `POST /extract/segments` y la degradación por modelo en `/schema` y `/graph` —
  commit `250e228`. Un modelo irresoluble ya no tumba la respuesta entera: los demás
  se sirven y el roto se declara en `unavailable` con su razón.

El prototipo que servía de referencia ejecutable (`dev/segments_prototype.py` y
`dev/reference_server.py`) fue **borrado**: existía solo mientras estos endpoints no
eran reales. Este documento queda como registro del diseño, no como pendiente.

## Tesis

La UI necesita ver un documento como una secuencia de **literales** (texto del template)
y **fields** (dirección, marcador, offsets de carácter). Esa secuencia la conoce el
renderer: es el único que sabe dónde escribe cada valor. No se parsea nada nuevo:
**se instrumenta el render**.

El prototipo lo demuestra sin tocar SLDB (parchea el renderer en runtime). Validado
contra los 1394 documentos del store del repo en `d877dad`:

- texto reconstruido == `render_model_markdown(...)` en 1394/1394
- 1392/1394 además idénticos al archivo en disco (los 2 restantes son `RequestDoc` con diff real)
- 18481 spans de fields `rev`/`optrev` string calzan con su valor; las 1611 diferencias son
  serialización YAML en frontmatter (comillas, líneas plegadas), esperables: la UI edita `value`, no `text`

## Entorno y restricciones

- Baseline en mi checkout (`d877dad`): `1055 passed, 2 skipped`. Verificar la propia con `lab-test.sh`.
- Reglas del repo: 1 clase por archivo, funciones ≤10 líneas, archivos ≤80 líneas efectivas,
  Pydantic en las fronteras, docstrings Google, sin mocks.
- Sin dependencias nuevas.

## Contrato

Modelos Pydantic nuevos en `sldb.api.segments` (un modelo por archivo):

```
DocumentSegments { id, doc, model, path, text, canonical: bool|None, payload, segments: [Segment] }

Segment = LiteralSegment { type:"literal", start, end, text }
        | FieldSegment   { type:"field", start, end, text, path, marker, traits, editable,
                           display: "inline"|"block", kind?, value?, source: SourceRef|None,
                           composition?: CompositionSpec, children: [Segment] }
        | CompositionPiece { type:"composition", start, end, text, path:"", marker:"compose",
                             traits, editable:false, display, source: SourceRef,
                             ref_index, ref, children: [Segment] }

SourceRef       { doc: str|None, path, model }
CompositionSpec { name, source_field, model, ref: "document"|"field" }

ExtractionSegments { model, text, payload, canonical_text,
                     fields: [FieldSegment sin children + alignment:"exact"|"approximate"],
                     unmatched: [{start, end, text}], coverage: float }
```

Semántica:

- Offsets de carácter sobre `text`, que es el **render canónico** del payload.
- `path` usa el espacio de `sldb fields`: `title`, `tags/0`, `steps/2/title`.
- `value` es el valor tipado. `text` es su superficie. La UI edita `value`.
- `editable` = `marker in {rev, optrev}`. Sale del template, no de la UI.
- `display = "block"` cuando el field ocupa su propio bloque (línea en blanco antes y después, o borde del documento).
- `kind` según `sldb.api.schema.field_kinds` (ítem de `stringlist` → `string`).
- `canonical` = el archivo en disco (sin espacios finales) coincide con `text`.
- Segmentos anidados: los hijos quedan en `children` con literales intercalados.
  **Desempate a igual tramo: el envuelto después es el de afuera.** Sin esto, una composición
  con una sola pieza pone la pieza por fuera del field `render` (bug real encontrado en el prototipo).

## Parte A · Render instrumentado

1. `core/renderer_engine/span_recorder.py` → `SpanRecorder`.
   - `wrap(text, meta) -> str`: registra `meta` y devuelve `U+E000 <id> U+E001 <text> U+E002`.
   - Lleva un prefijo de path para ítems de lista (`root/i`, y si el ítem es escalar el path es solo `root/i`).
2. Inyección explícita (default `None` = cero cambio de comportamiento):
   - `SLDBRenderer(recorder=None)` lo pasa a `ListRenderer`, `TableRenderer`, `YamlRenderer`.
   - `BaseRenderer._sub_marker`: si hay recorder y el marcador se resolvió (salida ≠ marcador
     literal), envolver la salida. Un `optrev` en `None` que deja string vacío genera un span de
     largo 0: la UI lo usa como punto de inserción.
   - `ListRenderer._render_items`: fijar el prefijo por ítem.
   - `YamlRenderer._render_frontmatter_line`: envolver lo que va después de `key:` (el valor ya dumpeado).
   - `StructuredNLDoc.render_payload(recorder=None)` → `compose_field(name, recorder=None)`.
3. Decodificador `core/segments/sentinel_decoder.py`: quita centinelas y devuelve `(texto, spans)`.
   **Decodificar antes del `.strip()` final** de `SLDBRenderer.render` y ajustar offsets en el strip:
   si se hace después, un valor al final del documento con espacios finales queda corrido.
4. Constructor del árbol (`core/segments/segment_tree.py`) + literales intercalados.
5. `sldb.api.build_document_segments(store_path, pythonpath, doc) -> DocumentSegments`.
6. Ruta `GET /document/segments?id=<doc>` en `cli/serve` (404 doc desconocido, 422 si no renderiza).

Test invariante: para todo documento del store del repo, el texto decodificado es igual a
`render_model_markdown(model, payload)` byte a byte.

## Parte B · Extracción sobre texto crudo

`POST /extract/segments {model, markdown}`:

1. `extract_model_data(model, markdown)` → payload.
2. Render instrumentado del payload → texto canónico + spans.
3. Alineación a nivel de carácter canónico → crudo con `difflib.SequenceMatcher(autojunk=False).get_opcodes()`.
   - Span con ambos bordes en tramos `equal` → `exact`; si no → `approximate` (borde al inicio/fin del tramo).
   - `unmatched`: tramos `insert`/`replace` del lado crudo **recortados de espacios**, descartando los vacíos.
   - `coverage` = caracteres cubiertos por fields / largo del texto sin espacios de borde.

Es código nuevo: `api/matching/difflib_matcher.py` calcula similitud, no alineación.

## Parte C · Procedencia de composición

Con recorder, `compose_field`:

- el marcador `render` de una composición lleva `composition {name, source_field, model, ref:"document"}`;
- cada pieza se envuelve como `CompositionPiece` con `source {path, model, doc}`, `ref_index`, `ref`;
- dentro de la pieza, los valores del payload hijo se envuelven antes del `.format(**p)` con su
  path del hijo; `editable` si el field está en los rev fields del modelo hijo.

`source.doc` se resuelve contra el índice del store (ruta → nombre de documento). Pieza no
trackeada → `doc: null` y la UI la muestra en solo lectura.

## Parte D · Atom = field tipado

- Dirección de atom: `docs/<doc>/<field_path>`, la misma de `sldb fields`.
- Nuevo modo de composición: `{"source_field": "atoms", "ref": "field", "template": "{value}"}`
  donde cada ref es una dirección de atom.
- Resolverlo necesita contexto de store: el render recibe un `FieldRefResolver` inyectado
  (misma necesidad que H2 de la propuesta: que el modelo conozca su store). Sin resolver, el
  field compuesto rinde vacío, igual que hoy con una ruta inexistente; como es `render`, no
  afecta la validación.
- Segmentos: `ref:"field"` en `CompositionSpec`; cada pieza con `source {doc, path: field_path, model}`.

La UI ya dibuja y edita piezas de forma genérica. Lo único que cambia en la UI con D es el
selector de "agregar pieza", que pasará a listar atoms vía `/find?type=field`.

## Hallazgos a resolver (no bloquean A–C)

1. **`/schema` se cae entera si un modelo no importa.** En el repo pasa con `deskops.models`.
   Debe degradar por modelo y devolver `errors: [{model, error}]` (el servidor de referencia ya lo hace).
2. **`/schema` no expone `description` por field**, aunque es obligatoria en el contrato del modelo.
   Agregarla al descriptor. La UI la usa como ayuda y placeholder.
3. **Los refs de composición se resuelven contra el CWD del proceso** (`Path(ref).exists()`).
   Deben resolverse contra la raíz del proyecto.
4. **El texto compuesto queda persistido en el archivo del padre y se desactualiza.** Al editar
   una decisión, `acuerdos.md` en disco sigue con el texto viejo hasta que alguien re-guarda el
   padre (la UI lo muestra como `canonical: false`). La propuesta asumía que el padre no guarda
   copia; en disco sí la guarda. Decidir: re-renderizar los padres al guardar un hijo (requiere
   índice inverso de composiciones) o dejar de persistir los fields `render` compuestos.

## Done when

- A, B y C con tests usando los modelos de `tests/test_composition.py` + el invariante sobre todo el store.
- Caso de borde cubierto: composición de una sola pieza (desempate a igual tramo).
- Baseline verde; `test_clean_code_rules` verde con los archivos nuevos.
- Las respuestas validan contra `src/core/contract.ts` de la UI: se puede apagar
  `dev/reference_server.py` y apuntar la UI a `sldb serve` sin cambios.
