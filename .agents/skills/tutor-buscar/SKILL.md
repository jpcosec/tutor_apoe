---
name: tutor-buscar
description: >-
  Busca en la base de conocimiento APOS/APOE y muestra qué dice, con su fuente. Úsala
  cuando alguien pregunta "qué dice la base sobre…", "busca…", "muéstrame el átomo…",
  "qué hay de encapsulación / esquema / descomposición genética…", o quiere saber si un
  tema ya está cubierto antes de agregarlo.
---

# Buscar en la base APOS

La base está hecha de **átomos**: una afirmación corta, con su pregunta, su respuesta y la
procedencia (de qué parte del libro salió). Los átomos cuelgan de **ramas** temáticas.

## Cómo buscar

```bash
export TUTOR_EMBEDDER=hash
tutor kb rank --kb kbs/apos "la pregunta o el tema, tal como lo dijo la persona" --k 8
tutor kb show <id-del-átomo> --kb kbs/apos      # el átomo completo, en JSON
```

`rank` devuelve una tabla `id / score / title`. Para los 3–5 mejores, abre cada uno con
`show` y lee la respuesta y la procedencia.

Si `tutor` no existe, usa primero la skill `tutor-preparar`.

## Cómo responder

- En español y sin jerga técnica: nada de JSON, ids largos ni puntajes salvo que los pidan.
- Por cada átomo relevante: el título, la respuesta en una o dos frases y la procedencia
  (capítulo o sección de la fuente).
- Responde solo con lo que está en la base. Si la base no cubre el tema, dilo claramente y
  ofrece cargarlo con la skill `tutor-cargar-fuente`; no completes con conocimiento propio
  como si viniera de la base.
- Si la persona quiere verlo en el mapa, usa la skill `tutor-abrir-visor`.
