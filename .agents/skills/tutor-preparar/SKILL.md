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

1. Trae lo último: `git pull --ff-only origin main`. Si falla porque hay cambios locales sin
   guardar, no los descartes: usa la skill `tutor-guardar-cambios` o pregunta.
2. Comprueba si ya está instalado: `tutor --help`. Si responde, salta al paso 4.
3. Instala (tarda unos minutos):
   ```bash
   ./scripts/bootstrap_deps.sh        # trae sldb y pron a third_party/ (necesita la herramienta `repo`)
   pip install -r requirements.txt    # instala el tutor y sus paquetes
   ```
   Si `repo` no existe o `bootstrap_deps.sh` no puede descargar, detente y dile a la persona
   que le pida ayuda a JP: es un problema de acceso, no algo que debas rodear.
4. Reconstruye y valida la base (unos 2 minutos, no usa internet):
   ```bash
   export TUTOR_EMBEDDER=hash
   tutor kb build
   tutor kb validate --kb kbs/apos
   ```
   Debe terminar con `KB válida`. Si la validación lista errores `hash_d no calza`, es que la
   base derivada quedó vieja: `tutor kb build` lo arregla.
5. Prueba una pregunta sin gastar nada: `tutor ask --kb kbs/apos --model test "¿Qué es una acción?"`.

## Qué decirle al terminar

Que el tutor quedó listo, cuántos documentos tiene la base (lo imprime `validate`) y qué
puede pedir ahora: buscar en la base, abrir el visor, cargar una fuente nueva o guardar
cambios.

## Claves

`--model test` no necesita claves ni internet. Para respuestas reales del tutor hace falta
`DEEPSEEK_API_KEY` (ver `.env.example`). Nunca escribas una clave en un archivo del
repositorio ni la muestres en pantalla.
