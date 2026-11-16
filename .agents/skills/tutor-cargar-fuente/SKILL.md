---
name: tutor-cargar-fuente
description: >-
  Incorpora conocimiento nuevo a la base APOS desde una fuente (PDF, texto o Markdown):
  la ingiere, propone átomos con su cita, los revisa con la persona y aprueba los que
  ella acepte. Úsala cuando alguien dice "carga este PDF", "agrega este capítulo",
  "falta tal tema en la base", "propón átomos sobre…", "revisemos los propuestos" o
  "aprueba / rechaza este átomo".
---

# Cargar una fuente y sumar átomos

Regla del proyecto: **todo átomo debe poder rastrearse a una fuente**, y nada de lo
propuesto llega al tutor hasta que una persona lo aprueba. Tú propones; la persona decide.
Detalle completo en `docs/compiler.md`.

## Flujo

1. **Ingerir la fuente** (una vez por documento). Copia el archivo a `sources/` si no está ahí.
   ```bash
   tutor compile ingest sources/<archivo>.pdf --kb kbs/apos --title "Autor (año) Título"
   ```
2. **Pedir átomos** sobre un tema o una pregunta de estudiante. Empieza siempre en seco:
   ```bash
   tutor compile run "el tema, con las palabras de la persona" --kb kbs/apos --max 5 --dry-run
   ```
   Este paso usa el modelo de `TUTOR_MODEL` y necesita su clave (ver `.env.example`). Si no
   hay clave, dilo y detente; no inventes átomos a mano.
3. **Mostrar las propuestas** en lenguaje simple: título, respuesta, de qué página o
   fragmento sale y a qué rama iría. Señala las que el compilador marcó como parecidas a un
   átomo existente o sin respaldo claro.
4. Si la persona quiere seguir, repite sin `--dry-run` para dejarlas como propuestas, y
   revisa con:
   ```bash
   tutor compile list --kb kbs/apos --status proposed
   tutor compile show <id> --kb kbs/apos
   ```
5. **Aprobar o rechazar** solo lo que la persona indique, una decisión por átomo:
   ```bash
   tutor compile approve <id> [<id>…] --kb kbs/apos
   tutor compile reject <id> --why "motivo breve" --kb kbs/apos
   ```
6. **Validar**: `tutor kb validate --kb kbs/apos` debe decir `KB válida`.
7. Ofrece guardar con la skill `tutor-guardar-cambios`.

## Cuidados

- No apruebes por tu cuenta, ni "todos de una": pregunta.
- No edites a mano los archivos de `kbs/apos/` ni de `.sldb/`; usa los comandos.
- Un átomo es **una sola afirmación** (respuesta de 80 palabras como máximo). Si una
  propuesta mezcla dos ideas, recházala y vuelve a pedir con un tema más acotado.
- Para saber qué le falta a la base: `tutor compile gaps --questions benchmarks/apos_questions.yaml --kb kbs/apos`.
