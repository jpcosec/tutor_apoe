---
name: tutor-abrir-visor
description: >-
  Abre la interfaz web del Tutor APOE en el navegador: el chat con el tutor, el grafo o
  mapa de la base, la carga de paquetes, las notas y la configuración del tutor. Úsala
  cuando alguien pide "abrir el tutor", "ver el grafo", "ver el mapa", "abrir el visor",
  "conversar con el tutor", "mostrar la página" o "cambiar cómo responde el tutor".
---

# Abrir el visor

Ejecuta desde la raíz del repositorio y deja el servidor corriendo en segundo plano:

```bash
export TUTOR_EMBEDDER=hash
tutor web --kb kbs/apos --model test --port 8300
```

Luego dale a la persona el enlace <http://127.0.0.1:8300> y explícale las pestañas:

- **Conversación**: chat con el tutor; "Ver contexto" muestra qué átomos usó para responder.
- **Paquetes**: subir una fuente (PDF o página) y prepararla por etapas.
- **Grafo APOS**: el mapa de ramas y átomos; al elegir una tarjeta se puede editar.
- **Scratch**: notas personales que quedan en ese navegador.
- **Configuración**: quién es el tutor y qué normas sigue al responder, como una página con
  campos. Se guarda al salir de cada campo y vale desde la pregunta siguiente. Los átomos y
  ramas se ven ahí, pero no se cambian (eso es en Grafo APOS o con `tutor-cargar-fuente`).

Enlaces directos: `/#chat`, `/#packages`, `/#graph`, `/#scratch`, `/#config`. Para resaltar átomos en
el grafo: `/graph?highlight=atom-a,atom-b`.

## Detalles

- `--model test` responde con texto de prueba y no gasta. Para respuestas reales quita
  `--model test`; necesita `DEEPSEEK_API_KEY` configurada (ver `.env.example`). Si no hay
  clave, avisa y sigue con `test`.
- Si el puerto 8300 está ocupado, es probable que el visor ya esté abierto: comprueba el
  enlace antes de levantar otro; si no, usa `--port 8301`.
- Si `tutor` no existe o la base no valida, usa primero la skill `tutor-preparar`.
- Si la pestaña Configuración dice que la wiki no está disponible, lee el motivo en la misma
  página: el resto del visor funciona igual. Nunca cambies `--host`; fuera de esta máquina la
  configuración exige una clave (`TUTOR_WIKI_KEY`).
- Para detenerlo, termina el proceso que dejaste corriendo. Si la persona editó átomos en el
  grafo o cambió la configuración del tutor, ofrécele guardar los cambios con la skill
  `tutor-guardar-cambios`.
