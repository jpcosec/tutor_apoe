---
name: SLDB Workbench
description: La UI de SLDB. Prosa de papel con fierros ocultables.
colors:
  paper: "#FAF9F6"
  stone: "#F4F3EF"
  tint: "#EFECE6"
  card: "#FFFFFF"
  hairline: "#E6E4DD"
  border: "#D4D2CC"
  ink: "#1A1A1A"
  ink-body: "#2C2C2A"
  ink-muted: "#73726E"
  ink-tertiary: "#9C9A94"
typography:
  display:
    fontFamily: "Newsreader, Georgia, Cambria, serif"
    fontSize: "30px"
    fontWeight: 500
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  headline:
    fontFamily: "Newsreader, Georgia, Cambria, serif"
    fontSize: "20px"
    fontWeight: 500
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Newsreader, Georgia, Cambria, serif"
    fontSize: "12.5px"
    fontWeight: 600
  body:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.68
  quote:
    fontFamily: "Newsreader, Georgia, Cambria, serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, monospace"
    fontSize: "12px"
    fontWeight: 400
  label-gutter:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, monospace"
    fontSize: "9.5px"
    fontWeight: 400
    lineHeight: 1.35
  label-caps:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, monospace"
    fontSize: "10px"
    fontWeight: 500
    letterSpacing: "0.05em"
rounded:
  sm: "2px"
  none: "0px"
spacing:
  topbar-height: "44px"
  rail-height: "24px"
  sheet-max: "672px"
  sheet-pad: "48px"
  gutter-col: "140px"
  block-gap: "28px"
components:
  button:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "4px 10px"
  button-hover:
    backgroundColor: "{colors.stone}"
    textColor: "{colors.ink}"
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sm}"
    padding: "4px 10px"
  lens-link:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  lens-link-active:
    backgroundColor: "{colors.stone}"
    textColor: "{colors.ink}"
  chip:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.sm}"
    padding: "1px 5px"
  chip-ink:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "5px 8px"
  transclusion-card:
    backgroundColor: "{colors.stone}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "14px 16px"
  topbar:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    height: "44px"
  bottom-rail:
    backgroundColor: "{colors.stone}"
    textColor: "{colors.ink-muted}"
    height: "24px"
---

# Design System: SLDB Workbench

## Overview

**Creative North Star: "Mundo de papel con fierros ocultables"**

El Workbench es una hoja de papel cálido sobre la que se lee un documento como en un libro, y
una segunda capa de ingeniería que se enciende al lado sin moverlo. En la lente Lectura queda
solo la prosa: título en serif, cuerpo en sans, una columna de 672 px. En la lente Fierros la
misma página gana una canaleta marginal en mono que dice qué es cada bloque (`field:`,
`transclude:`, `spec2viz:`) y con qué operación se escribe. Nada se reacomoda al cambiar de
lente; la estructura se suma al margen.

El sistema es monocromo y plano. No hay color de acento: la jerarquía se construye con tres
tintas, líneas de un píxel y el contraste entre tres familias tipográficas con roles fijos. La
serif es la voz del documento, la sans es su cuerpo, la mono es la voz de la máquina.

Este registro describe el sistema implementado en `src/styles/paper-tokens.css` y las cuatro
vistas de `src/workbench/`. Los nombres descriptivos de colores y reglas son del redactor de
este archivo y están pendientes de revisión del dueño.

**Key Characteristics:**
- Papel cálido, sin blanco puro de fondo ni negro puro de texto.
- Monocromo: ningún color de acento ni códigos de semáforo.
- Tres familias con rol fijo: Newsreader (documento), Inter (cuerpo), JetBrains Mono (máquina).
- Plano: líneas de 1 px en vez de sombras; una sola sombra, en la paleta de comandos.
- Esquinas casi rectas (2 px).
- Densidad doble: prosa holgada a 16 px junto a metadatos mono de 8.5 a 12 px.

## Colors

Una escala de grises cálidos, del papel a la tinta, sin matiz de acento.

### Primary
- **Tinta** (`ink`): el único "color" de énfasis. Texto de títulos, borde izquierdo de un
  bloque editable y de una ficha transcluida, fondo del botón primario y del chip `ROOT`,
  borde de la paleta de comandos y del control con foco.

### Neutral
- **Papel cálido** (`paper`): fondo de la aplicación, de la hoja de lectura y de la cabecera.
- **Piedra suave** (`stone`): panel izquierdo (árbol espacial y esquema), riel inferior, fondo
  de hover y de la lente activa, lavado de las fichas transcluidas al 65 %.
- **Tinte** (`tint`): hover sobre piedra y chip de lavado.
- **Ficha** (`card`): fondo de botones y de la píldora de contexto; el único blanco puro, y
  solo en superficies pequeñas.
- **Línea fina** (`hairline`): divisores de cabecera, riel y encabezado de ficha.
- **Borde** (`border`): contorno de controles, fichas y nodos del árbol; separadores `/` y `·`.
- **Tinta de cuerpo** (`ink-body`): párrafos y valores de campo.
- **Gris técnico** (`ink-muted`): etiquetas mono, canaleta de fierros, texto secundario.
- **Gris terciario** (`ink-tertiary`): segunda línea de la canaleta, rutas y modelos de apoyo.

### Named Rules
**La regla de la tinta única.** El énfasis se hace con tinta, peso o una línea, nunca con un
matiz. Verde, ámbar y rojo no existen en este sistema: un error se marca con borde de tinta y
texto, no con color.

**La regla del blanco escaso.** El blanco puro solo aparece en fichas y botones pequeños. Una
superficie grande es papel o piedra.

## Typography

**Display Font:** Newsreader (con Georgia, Cambria)
**Body Font:** Inter (con la sans del sistema)
**Label/Mono Font:** JetBrains Mono (con la mono del sistema)

**Character:** una serif editorial para lo que el documento dice de sí mismo, una sans neutra
para leerlo y una mono para todo lo que viene de SLDB. Las tres conviven en la misma línea de
visión sin competir porque nunca intercambian roles.

### Hierarchy
- **Display** (500, 30 px, interlínea 1.25, tracking -0.015em): el título del documento abierto.
  Uno por página.
- **Headline** (500, 20 px, tracking -0.01em): encabezados de sección dentro de la prosa.
- **Title** (600, 12.5 px, Newsreader): nombre del documento dentro de un nodo del árbol
  espacial.
- **Body** (400, 16 px, interlínea 1.68, Inter): prosa y valores de campo. La columna mide
  672 px como máximo.
- **Quote** (400 cursiva, 16 px, interlínea 1.6, Newsreader): el texto de una pieza transcluida.
- **Label** (400 a 600, 12 px, mono): cabecera, migas, lentes, tablas de esquema.
- **Label de canaleta** (400, 9.5 px y 8.5 px, mono): metadatos de fierros en el margen.
- **Label en mayúsculas** (500, 10 px, tracking 0.05em, mono): encabezados de bloque
  (`DIAGRAMA DE DECISIÓN RENAL`) y rótulos de grupo.

### Named Rules
**La regla de las tres voces.** Serif: el documento. Sans: su cuerpo. Mono: la máquina. Un
identificador, hash, modelo, operación o atajo siempre va en mono; un título nunca.

**La regla del corchete.** El estado activo de un conmutador en mono se escribe entre
corchetes (`[ Estructura / Fierros ]`, `[ Vista ]`), además del fondo de piedra.

## Layout

Aplicación a pantalla completa, sin scroll de página: cabecera de 44 px, cuerpo partido en dos
paneles y, en algunas vistas, un riel inferior de 24 px. El Workbench parte 38/62 (árbol
espacial a la izquierda, prosa a la derecha); las vistas de anclaje y diagramas parten 48/52.
Cada panel hace su propio scroll.

La hoja de lectura es una columna centrada de 672 px con 48 px de aire. En la lente Fierros la
columna reserva 140 px a la izquierda para la canaleta marginal, que se alinea a la derecha
contra una línea vertical de 1 px. Los bloques se separan 28 px (24 px en Lectura). Los
metadatos nunca empujan la prosa: viven en el margen.

No hay breakpoints definidos; el sistema está pensado para escritorio.

## Elevation & Depth

Plano. La profundidad se expresa con el cambio de papel a piedra y con líneas de 1 px, no con
sombras. La única sombra del sistema está en la paleta de comandos, junto con el único velo
(tinta al 32 % con desenfoque de 2 px).

### Shadow Vocabulary
- **Paleta** (`box-shadow: 0 12px 32px rgba(0, 0, 0, 0.14)`): solo el modal de ⌘K.

### Named Rules
**La regla de la línea.** Dos superficies se separan con una línea de 1 px o con el paso de
papel a piedra. Una sombra indica que algo flota sobre la página, y solo la paleta flota.

## Shapes

Rectangular. Radio de 2 px en botones, chips, fichas, nodos y modales; 0 px en campos de
texto. Bordes de 1 px. La única línea de 2 px es el borde izquierdo de tinta de una ficha
transcluida. El fondo del Model Studio usa una cuadrícula de papel de 24 px.

## Components

Contenidos y tipográficos: casi todos los controles son texto mono con un borde fino.

### Buttons
- **Shape:** esquina casi recta (2 px), borde de 1 px.
- **Default:** fondo de ficha, texto de tinta en mono de 11 px, relleno 4 px 10 px.
- **Primary:** fondo de tinta, texto de papel; al pasar el cursor, negro.
- **Hover:** borde de tinta y fondo de piedra, en 100 ms. **Disabled:** opacidad 0.4.

### Chips
- **Style:** mono de 9.5 px, borde fino, fondo de papel y texto gris técnico.
- **Variantes:** de tinta (fondo de tinta, texto de papel) y de lavado (fondo de tinte).

### Cards / Containers
- **Ficha transcluida:** lavado de piedra, borde fino, borde izquierdo de tinta de 2 px, radio
  2 px, relleno 14 px 16 px. Encabezado en mono de 10 px sobre una línea fina; cita en serif
  cursiva.
- **Nodo del árbol:** fondo de papel o ficha, borde fino; el nodo raíz lleva borde de tinta y
  un chip `ROOT`.
- **Shadow Strategy:** ninguna (ver Elevation & Depth).

### Inputs / Fields
- **Style:** fondo de papel, borde fino, sin radio, mono de 12 px.
- **Focus:** el borde pasa a tinta. No hay halo.
- **Campo editable en prosa:** no es una caja; es el texto mismo con una línea vertical de
  tinta en la canaleta.

### Navigation
- **Cabecera:** 44 px, mono de 12 px. Migas `sldb / Modelo / documento` a la izquierda;
  conmutador de lentes y accesos a la derecha.
- **Lentes:** enlaces mono separados por puntos; el activo va entre corchetes, con fondo de
  piedra y borde fino. Transición de 120 ms.
- **Paleta ⌘K:** modal de 580 px con borde de tinta sobre un velo.

### Canaleta de fierros
El componente propio del sistema. Columna de 136 px a la izquierda de cada bloque, alineada a
la derecha, en mono de 9.5 px: primera línea, qué es el bloque (`field: objetivo`); segunda,
en 8.5 px y gris terciario, la operación que lo escribe (`POST /save · expected ec16670`).
Solo existe en la lente Fierros.

## Do's and Don'ts

### Do:
- **Do** poner todo metadato de SLDB (dirección, modelo, hash, operación) en mono y en el
  margen o la cabecera, fuera de la columna de prosa.
- **Do** separar superficies con una línea de 1 px o con el paso de papel a piedra.
- **Do** marcar el estado activo con corchetes, peso y fondo de piedra.
- **Do** usar los tokens `--wb-*`; hoy hay hex escritos a mano en `TopologyMindmap.tsx` y
  `ModelStudioView.tsx` que deben volver a ellos.

### Don't:
- **Don't** introducir un color de acento ni colores de estado tipo semáforo.
- **Don't** usar sombras fuera de la paleta de comandos.
- **Don't** mostrar puertos, hashes, botones de estado REST o cajas de consola dentro del área
  de lectura; eso es justo lo que la lente Fierros existe para ocultar.
- **Don't** redondear más allá de 2 px.
- **Don't** usar la serif para identificadores ni la mono para títulos.
