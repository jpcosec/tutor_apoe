# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Quien trabaja un store SLDB: lee sus documentos, los edita, ancla átomos sobre fuentes, sigue
diagramas hasta lo que los justifica y evoluciona los modelos. El store puede ser de cualquier
dominio; no hace falta que sea un desk de deskops.

Sin confirmar todavía: si el usuario objetivo incluye a expertos de dominio no técnicos (por
ejemplo quien redacta un informe clínico) o solo a quien ya conoce SLDB.

## Product Purpose

Es la UI de SLDB. Muestra cualquier documento de un store como prosa legible y deja trabajarlo
sin salir de ella: editar los campos en el lugar, editar una pieza transcluida en su documento
de origen, inspeccionar un diagrama y sus nodos, extraer átomos de un texto fuente y diseñar o
promover modelos.

Funciona si una persona completa esos cuatro flujos contra un store real sin abrir una terminal
ni un archivo, y sin que la interfaz le muestre maquinaria que no pidió ver.

## Positioning

La interfaz general de SLDB, autónoma primero (confirmado por el dueño, 2026-11-17): sirve sola
contra cualquier store. No es una pantalla de deskops ni es específica de deskops; abrirla desde
la UI de deskops es un caso de uso más.

Lo que una UI vecina no puede copiar: el documento que se lee es el mismo objeto tipado del
store. Cada campo, transclusión y diagrama en pantalla tiene dirección, modelo y hash, y esos
"fierros" se pueden encender o apagar sin cambiar de vista.

## Operating Context

- Se levanta contra un `sldb serve` (proxy `/sldb`); en desarrollo, con Vite.
- Cuatro vistas: Workbench (árbol espacial + prosa), Inspector de diagramas, Extracción y
  Anclaje, Model Studio. Tres lentes: Lectura, Estructura/Fierros, Esquema.
- El dominio de las maquetas y del store demo es "Levira" (un informe clínico compuesto de
  átomos). Es un ejemplo, no el producto.
- La app anterior (documento, composición, extracción, salud, bandeja, lector, destilación)
  sigue detrás de `#/legacy`; su destino es una decisión abierta del dueño.

## Capabilities and Constraints

- Lee y escribe solo por la API de `sldb serve`; nunca escribe Markdown ni archivos.
- Guardar un documento es `POST /save` con `expected`; SLDB re-renderiza y verifica el
  round-trip.
- Contrato de capas (`contracts/layers.json`, verificado por `scripts/check-layers.mjs`):
  `src/core` sin React ni librerías visuales; las vistas no hacen fetch directo.
- Sin mocks ni datos inventados en la entrada de producción: sin servidor, la interfaz lo dice
  y queda vacía.
- Abierto: la integración con deskops (volver al desk, estado de workflow, verbos) y cómo se
  ve la autoridad de escritura por modelo. El dueño no las fijó como compromisos al confirmar
  este documento.

## Brand Commitments

- Nombre: SLDB Workbench.
- "Mundo de papel con fierros ocultables" (confirmado): lectura limpia por defecto; los
  metadatos de SLDB aparecen solo en la lente Fierros.
- Idioma de la interfaz y de la documentación: español.

## Evidence on Hand

- Especificación y manual: `../docs/ui-workbench/MANUAL_DE_USUARIO_Y_ESPECIFICACION_UI.md`.
  Su sección 2 presenta el Workbench como superficie de la UI de deskops; el dueño corrigió
  ese marco el 2026-11-17 (ver Positioning). El resto del manual sigue siendo referencia.
- Maquetas de las cuatro vistas, con captura: `../docs/ui-workbench/screens/`.
- Store demo Levira: `../workbench_demo/`, generado por
  `../scripts/setup_workbench_demo_store.py`.
- Tests: 29 archivos de vitest (396 tests) y el contrato de capas.
- No hay usuarios externos, métricas de uso ni testimonios: no inventarlos.

## Product Principles

1. **Papel con fierros ocultables.** Primero se lee; la estructura se enciende cuando se
   necesita y se apaga sin perder el lugar.
2. **Toda escritura tiene nombre.** Ningún control escribe archivos: cada acción que muta
   invoca una operación nombrada del servidor dueño, y la interfaz la muestra junto con su
   resultado.
3. **La UI no calcula.** SLDB entrega documentos, segmentos, grafo, notaciones y contratos; la
   interfaz no reimplementa ni recalcula lo que el servidor sabe. Si falta una operación, se
   pide al repo dueño.
4. **General antes que específica.** Cualquier store SLDB, de cualquier dominio; nada en la
   interfaz depende de un desk ni de un dominio de ejemplo.
