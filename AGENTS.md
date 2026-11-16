# Trabajo en Tutor APOE

Este repositorio es una base de conocimiento sobre la teoría APOS. Mantén el
trabajo pequeño, trazable a una fuente y separado de cualquier runtime de
chatbot.

## Regla de entrega

Cada cambio terminado debe quedar publicado en el remoto:

1. Ejecuta la validación más pequeña que corresponda.
2. Haz `git add` únicamente de los archivos del cambio.
3. Crea un commit claro.
4. Ejecuta `git push origin <rama-actual>`.

No dejes cambios terminados solamente en la máquina, salvo que la persona
usuaria pida expresamente no hacer commit o push. Nunca incluyas archivos
generados de `.sldb/runtime/`, credenciales ni cambios ajenos en ese commit.

## Interfaz de la KB

La interfaz para explorar y buscar la base es `scripts/kb.py`. No añade un
chatbot ni usa un modelo de lenguaje: delega la búsqueda a `sldb find` y
presenta los átomos fuente en un visor local.

## Skills para trabajar sin programar

En `.agents/skills/` hay skills que Codex (y otros agentes) cargan solos al abrir este
repositorio. Están pensadas para quien no programa: basta pedirlo con palabras propias o
escribir `$` y el nombre.

- `tutor-preparar` — instalar y comprobar que todo funciona.
- `tutor-buscar` — qué dice la base sobre un tema, con su fuente.
- `tutor-abrir-visor` — abrir el chat y el grafo en el navegador.
- `tutor-cargar-fuente` — ingerir un PDF y proponer, revisar y aprobar átomos.
- `tutor-guardar-cambios` — guardar y publicar el trabajo.
