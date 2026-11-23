# De dónde viene esta carpeta

Es una copia de `superficie/` del proyecto `minegocio` (commit `5c79077` del 2026-11-22), traída el 2026-11-22 para
que sea la interfaz de la wiki de configuración del Tutor APOE. Esa carpeta es, a su vez, una copia de la superficie
de sldb (`SLDB_1/sldb/surface`, commit `562847e2` del 2026-11-20) adaptada para quien no sabe de sldb. No se
sincroniza con ninguno de los dos orígenes: los cambios se hacen en esta copia.

Se copió lo versionado en ese commit: sin `node_modules/`, `dist/` ni cachés, y sin los cambios que `minegocio`
tenía sin commitear ese día.

## Qué se adaptó aquí

- **Qué es la wiki**: las páginas de configuración del tutor (`AgentDoc`). `src/core/tutor.ts` dice qué tipos son
  configuración y cómo se rotulan las carpetas de la base; tiene que calzar con `CONFIG_MODELS` de
  `src/tutor/wiki.py`.
- **El índice** (`src/core/wiki-index.ts`, `src/workbench/WikiIndex.tsx`): la configuración va primero; el resto de la
  base (átomos, ramas, relaciones, fragmentos) se muestra plegado por carpeta y en solo lectura.
- **Sin altas ni bajas**: se quitó «+ Agregar» y «Quitar esta página» (`NuevaPagina.tsx` y lo que la servía). Las
  páginas de configuración las siembra `tutor kb build`; el servidor rechaza crear o quitar cualquier página.
- **Textos y rótulos**: la barra dice «Configuración · <nombre del tutor>», los campos del `AgentDoc` tienen rótulo
  en castellano (`src/workbench/Ficha.tsx`) y una página generada dice por qué no se edita.
- **Compilación** (`vite.config.ts`, `.env.production`): `npm run build` deja la interfaz en
  `../src/tutor/static/wiki/`, que va versionada, servida bajo `/wiki/` y hablando con `/api/wiki`.

Lo demás es del original, incluidos `README.md`, `DESIGN.md`, `PRODUCT.md`, las otras vistas (Fierros, Esquema,
anclaje, Spec2Viz) y sus pruebas. Desde la wiki del tutor esas vistas leen; lo que intenten escribir fuera de la
configuración lo rechaza el servidor.

## Recompilar

```bash
cd superficie && npm ci && npm test && npm run build
```
