# Decisión: la configuración del tutor se ve y se edita en una wiki

Fecha: 2026-11-22. Decide: JP.

## Qué se decide

`tutor web` gana una pestaña **Configuración**: una wiki donde el rol del tutor (su `AgentDoc`: encuadre,
instrucciones, proyección, políticas) se lee y se edita como un documento con campos. Lo guardado vale desde el
turno siguiente, sin reiniciar. La interfaz es la superficie de sldb tal como la adaptó `minegocio`, copiada a
[`superficie/`](../../superficie) (ver [`superficie/ORIGEN.md`](../../superficie/ORIGEN.md)).

## Por qué

- Quien ajusta el tutor no programa. Hasta ahora cambiar su encuadre era editar `apps/kb_agent/packs/apos/persona.md`
  y regenerar la base entera.
- La wiki de `minegocio` ya resolvió lo difícil: mostrar un documento sldb, dejar editar solo lo que el tipo marca
  como campo y guardar con `POST /save` y `expected`, que detecta si otra persona cambió la página mientras tanto.
  JP, sobre ella: «su ui de config por wiki creo que está extremadamente útil».

## Qué es configuración y qué no

- **Configuración (se edita aquí)**: las páginas `AgentDoc` de la KB. El modelo declara `__authority__ = "authored"`:
  texto escrito con intención, que una persona corrige. `tutor kb build` las siembra desde el pack la primera vez y
  después las conserva, igual que `ingest/` y `proposed/`. Para volver al texto del pack se borra `kbs/<kb>/agent/`
  y se regenera.
- **Todo lo demás (se ve, no se edita)**: átomos, ramas, relaciones, categorías, proyecciones. Su fuente es
  `desk/atoms/` y se gobierna con deskops; en la KB son `generated`. Editarlos en la wiki crearía una segunda fuente
  que la próxima regeneración borraría.

La lista de modelos de configuración está en dos lugares que tienen que calzar: `CONFIG_MODELS` en
`src/tutor/wiki.py` (lo que el servidor deja guardar) y en `superficie/src/core/tutor.ts` (lo que el índice muestra
como editable).

## Cómo se sirve

- `tutor web` lanza `python -m sldb serve` sobre el store de la KB como proceso hijo: solo en `127.0.0.1`, en un
  puerto libre, con un token de un solo uso (`SLDB_SERVE_TOKEN`) que no sale del proceso. Lo cierra al salir.
- El navegador nunca habla con sldb. Habla con `/api/wiki/…` del mismo servidor, que reenvía con el token. Pasan las
  lecturas (`GET`) y `POST save`; el resto de lo que sabe hacer `sldb serve` (cambiar tipos de página, crear
  documentos por otra ruta) responde 403.
- De un guardado solo pasan cambios (`update`) sobre páginas que hoy son de un modelo de configuración. El modelo se
  mira en la KB abierta, no en lo que dice el pedido. Crear, quitar o mover una página, y cualquier cambio sobre un
  átomo u otro documento generado, se rechaza con un mensaje que dice dónde se cambia eso.
- Tras un guardado se reabre la `KnowledgeBase` (la que está en memoria no ve lo que escribió otro proceso) y cada
  conversación usa la vigente en su turno siguiente. Si con el cambio la base deja de validar, o el rol se queda sin
  su página (alguien le cambió el `role`), el guardado se deshace con el `expected` del mismo pedido y la wiki dice
  por qué.
- La interfaz compilada va versionada en `src/tutor/static/wiki/`: quien usa este repo no tiene Node y la imagen
  Docker tampoco. Se recompila con `cd superficie && npm ci && npm run build`.
- Si falta la interfaz compilada o `sldb serve` no arranca, el resto de `tutor web` funciona y `/wiki/` dice qué falta.

## Acceso

`tutor web` no tiene autenticación y se usa en local. La wiki escribe las instrucciones del tutor, así que:

- Sin clave solo se abre cuando el servidor escucha en loopback (`--host 127.0.0.1`, el valor por defecto), y solo
  si se la pide como `127.0.0.1` o `localhost`.
- Si escucha en otra interfaz exige `TUTOR_WIKI_KEY` (16 caracteres o más) por HTTP Basic (cualquier usuario, la
  clave como contraseña) o Bearer, en `/wiki/…` y `/api/wiki/…`. Sin la variable esas rutas responden 503 y explican
  por qué. La comparación es en tiempo constante.
- Si `TUTOR_WIKI_KEY` está definida se pide siempre, también en loopback: sirve para publicar el tutor detrás de un
  proxy inverso que llega por `127.0.0.1`.
- Un pedido que llega desde otra página web (cabecera `Origin` distinta del servidor) se rechaza. El resto de
  `tutor web` permite CORS desde cualquier origen; sin esto, cualquier sitio abierto en el mismo navegador podría
  reescribir las instrucciones del tutor.

## Límites conocidos

- El `sldb serve` de la wiki y el propio `tutor web` (Grafo APOS, Paquetes) escriben el mismo store desde dos
  procesos. sldb toma un lock por escritura, pero cada proceso recuerda lo que leyó: tras un guardado por la wiki se
  le pide a sldb que vuelva a leer (`wiki.forget_store_reads`). En el otro sentido, lo que se edite en el Grafo
  puede no verse de inmediato en la wiki (no se probó ese cruce).
- Cada guardado reabre y valida la KB entera (unos 3 s con `kbs/apos`).
- Detrás de un proxy inverso que reescriba la cabecera `Host`, los guardados se rechazan por la comprobación de
  origen: el proxy tiene que conservar el `Host`.
- Las vistas de sldb que no son la lectura (Esquema, anclaje) siguen en la interfaz y leen; lo que intenten
  escribir lo rechaza el proxy.
