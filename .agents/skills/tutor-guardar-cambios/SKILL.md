---
name: tutor-guardar-cambios
description: >-
  Guarda y publica el trabajo hecho en el Tutor APOE (átomos nuevos o editados, fuentes
  cargadas) para que el resto del equipo lo vea. Úsala cuando alguien dice "guarda",
  "sube los cambios", "publica", "que JP lo vea", "sincroniza", o al terminar de aprobar
  átomos o editar en el grafo.
---

# Guardar y publicar cambios

La persona no usa git: hazlo tú y explícale el resultado sin jerga ("quedó guardado y el
equipo ya puede verlo"). Sigue la regla de entrega de `AGENTS.md`.

## Pasos

1. Mira qué cambió: `git status --short`. Resume en simple qué va a guardarse (por ejemplo,
   "3 átomos nuevos sobre el ciclo ACE y un PDF").
2. Valida la base: `TUTOR_EMBEDDER=hash tutor kb validate --kb kbs/apos`. Si no dice
   `KB válida`, no publiques: muestra el problema y arréglalo o pregunta.
3. Trae lo último del equipo: `git pull --rebase --autostash origin main`. Si aparece un
   conflicto, **detente**, no elijas un lado por tu cuenta y dile a la persona que avise a JP.
4. Agrega solo los archivos de este trabajo, por ruta:
   ```bash
   git add kbs/apos desk/atoms sources .sldb/core
   ```
   Ajusta la lista a lo que realmente cambió. **Nunca** incluyas `.sldb/runtime/`,
   `.sldb_cache/`, archivos `.env` ni claves, y no uses `git add -A`.
5. Revisa lo que quedó listo: `git diff --cached --stat`. Si aparece algo que no es de este
   trabajo, sácalo con `git restore --staged <ruta>`.
6. Crea el commit con un mensaje claro de una línea que diga qué se agregó y de qué fuente.
7. Publica: `git push origin main`.

## Si algo sale mal

- `push` rechazado: repite el paso 3 y vuelve a publicar. No uses `--force`.
- No borres ni descartes cambios (`git reset --hard`, `git checkout -- .`, `git clean`) para
  salir del paso: el trabajo sin guardar de la persona no se recupera.
