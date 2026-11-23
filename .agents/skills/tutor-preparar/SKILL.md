---
name: tutor-preparar
description: >-
  Deja el Tutor APOE listo para usar en esta máquina y comprueba que funciona. Úsala la
  primera vez que alguien abre el repositorio, cuando pide "instalar", "preparar", "dejar
  andando" o "poner al día" el tutor, o cuando otro comando falla con `tutor: command not
  found`, `No module named tutor` o "KB inválida".
---

# Preparar el Tutor APOE

La persona que te habla no programa. Haz tú los pasos, cuéntale en una frase qué estás
haciendo y no le pidas que escriba comandos. Ejecuta todo desde la raíz del repositorio.

## Pasos

1. Trae lo último: `git pull --ff-only`. Si falla porque hay cambios locales sin guardar, no
   los descartes: usa la skill `tutor-guardar-cambios` o pregunta.
2. Comprueba si ya está instalado: `./install.sh --check`. Si termina con `Todo en orden.`,
   salta al paso 4.
3. Instala (tarda entre 5 y 10 minutos): `./install.sh`. Crea `.venv/`, trae sldb y pron a
   `third_party/`, construye la base y la valida. Debe terminar con `Instalación lista.`.
   Si no puede descargar, detente y dile a la persona que le pida ayuda a JP: es un problema
   de acceso, no algo que debas rodear. Los mensajes de error más comunes están en
   `install.md`.
4. Prueba una pregunta sin gastar nada:
   `.venv/bin/tutor ask --kb kbs/apos --model test "¿Qué es una acción?"`.

Los comandos del tutor quedan en `.venv/bin/` (`.venv/bin/tutor`, `.venv/bin/tutor-mcp`).
Si la validación lista errores `hash_d no calza`, la base derivada quedó vieja:
`TUTOR_EMBEDDER=hash .venv/bin/tutor kb build` la reconstruye. Reconstruir no modifica
archivos versionados si los átomos no cambiaron.

## Qué decirle al terminar

Que el tutor quedó listo, cuántos documentos tiene la base (lo imprime `validate`) y qué
puede pedir ahora: buscar en la base, abrir el visor, cargar una fuente nueva o guardar
cambios.

## Claves

`--model test` no necesita claves ni internet. Para respuestas reales del tutor hace falta
`DEEPSEEK_API_KEY` (ver `.env.example`). Nunca escribas una clave en un archivo del
repositorio ni la muestres en pantalla.
