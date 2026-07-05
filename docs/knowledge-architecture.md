# Arquitectura de conocimiento

Este repo usa dos capas distintas:

## 1. Deskops como capa operativa

`desk/` se mantiene para:

- board
- tasks
- contexts/pills
- rituales de ejecución, testing y cierre

Esto sirve para gestionar el trabajo del proyecto.

## 2. SLDB como capa de conocimiento

La base de conocimiento ya no depende del `AtomDoc` de Deskops como modelo principal.

En cambio, este repo define modelos locales en:

- `knowledge_models/docs.py`

Y estructura los documentos en:

- `knowledge/source-notes/`
- `knowledge/atoms/`

## Modelos locales

### `SourceNoteDoc`

Sirve para capturar una nota pegada a una fuente concreta con localización precisa.

Campos principales:

- `source_path`
- `source_title`
- `chapter`
- `section`
- `page_start`
- `page_end`
- `anchor_text`
- `excerpt`
- `note`
- `tags`

### `KnowledgeAtomDoc`

Sirve para representar conocimiento ya destilado.

Campos principales:

- `id`
- `title`
- `question`
- `answer`
- `provenance`
- `tags`

`provenance` vive en el **frontmatter** y acepta una lista estructurada de referencias con:

- `source_path`
- `source_title`
- `chapter`
- `section`
- `page_start`
- `page_end`
- `anchor_text`
- `excerpt`

## Por qué este cambio

El `AtomDoc` de Deskops es útil para átomos simples, pero se queda corto cuando necesitamos:

- procedencia exacta
- trazabilidad a nivel de párrafo
- citas ancla reutilizables
- una base de conocimiento consultable con evidencia estructurada

Por eso:

- **Deskops** queda como capa operativa
- **SLDB + modelos locales** queda como capa de conocimiento

## Comandos útiles

### Ver modelos registrados

```bash
sldb models show SourceNoteDoc --store .sldb --pythonpath .
sldb models show KnowledgeAtomDoc --store .sldb --pythonpath .
```

### Reindexar luego de cambios

```bash
sldb stores update --store .sldb --pythonpath .
```

### Crear una nota fuente

```bash
sldb docs create --model SourceNoteDoc \
  -o knowledge/source-notes/apos/note-ejemplo.md \
  '{"id":"note-ejemplo","title":"Nota ejemplo","source_path":"sources/archivo.pdf","source_title":"Archivo","chapter":"1","section":"1.1","page_start":1,"page_end":1,"anchor_text":"Texto ancla","excerpt":"Cita breve","note":"Observación estructurada","tags":["system:apos","topic:example","layer:source","domain:mathematics-education"]}' \
  --store .sldb --pythonpath .
```

### Crear un átomo con procedencia estructurada

```bash
sldb docs create --model KnowledgeAtomDoc \
  -o knowledge/atoms/apos/atom-ejemplo.md \
  '{"id":"atom-ejemplo","title":"Átomo ejemplo","question":"what","answer":"Respuesta breve.","provenance":[{"source_path":"sources/archivo.pdf","source_title":"Archivo","chapter":"1","section":"1.1","page_start":1,"page_end":1,"anchor_text":"Texto ancla","excerpt":"Cita breve"}],"tags":["system:apos","topic:example","layer:theory","domain:mathematics-education"]}' \
  --store .sldb --pythonpath .
```
