# UX esperado — Conversador APOS con mesa determinista

## Objetivo

Diseñar una interfaz de **chat con inspector de contexto versionado**, donde cada respuesta del asistente esté asociada a una **mesa determinista** auditable.

La interfaz debe permitir:

- conversar con el sistema de forma natural
- inspeccionar el contexto exacto usado para cada respuesta
- navegar el razonamiento interno del sistema bibliotecario
- acceder al contenido atómico bajo demanda
- persistir referencias estructurales por id, no duplicar siempre el texto completo

---

## Modelo mental

La interfaz tiene **dos ritmos**:

1. **Interacción con usuario**
   - mensajes de usuario y respuestas del asistente
   - granularidad por turno conversacional

2. **Funcionamiento interno del sistema**
   - compilación de mesa
   - selección, retención, descarte y expansión de atoms
   - granularidad más fina que la conversación

Estos dos ritmos deben verse relacionados, pero no colapsados en una sola vista plana.

---

## Estructura general

## Columna izquierda
La columna izquierda es la **línea temporal conversacional**.

### Debe permitir
- scroll completo e independiente
- seleccionar una respuesta específica del asistente
- ver referencias `atom-...` en el texto
- activar el inspector derecho para esa respuesta

### Unidad principal
Cada respuesta del asistente representa una **unidad de trabajo** compuesta por:

- pregunta del usuario
- mesa compilada para responder esa pregunta
- respuesta generada desde esa mesa

### Requisitos visuales
Cada respuesta debería mostrar, de forma compacta:

- texto de respuesta
- referencias `atom-...`
- indicador de contexto asociado, por ejemplo:
  - cantidad de atoms
  - tags activos
  - cantidad de retained / removed
- estado de selección

---

## Columna derecha
La columna derecha es un **sidebar contextual abrible/cerrable**.

### No debe ser
- un panel fijo mostrando siempre el estado global actual
- un visor plano de un átomo
- una dump completa de toda la información al mismo tiempo

### Debe ser
- un inspector de la **mesa asociada a la respuesta seleccionada**
- independiente en scroll respecto de la izquierda
- reutilizable al cambiar la respuesta activa
- colapsable / expandible

---

## Relación izquierda ↔ derecha

La regla principal es:

- **cada respuesta del asistente queda ligada a una mesa distinta**
- al seleccionar una respuesta en la izquierda, la derecha muestra la mesa de esa respuesta
- al seleccionar otra respuesta, la derecha cambia de contexto

La derecha no muestra solo “la mesa actual del sistema”, sino la **mesa versionada de ese turno**.

---

## Principio de diseño del sidebar derecho

La derecha debe usar un patrón **matrioshka** de información:

- primero resumen
- luego detalle expandible
- luego modal para lectura larga

No mostrar todo siempre.

---

## Arquitectura de información del sidebar

# 1. Header contextual
Resumen de la mesa ligada a la respuesta seleccionada.

### Debe incluir
- pregunta del usuario
- id de mesa / id de compilación
- índice de turno o timestamp
- tags activos
- cantidad de atoms
- retained / removed
- criterio general de compilación

### Objetivo
Dar una comprensión rápida de qué contexto se está inspeccionando.

---

# 2. Sección “Train of Thought”
Representa el razonamiento del sistema bibliotecario.

## Importante
No tiene por qué ser el chain-of-thought crudo de un modelo.
Debe ser un **log auditable del proceso de compilación**.

### Debe mostrar en resumen
- tags detectados
- expansiones aplicadas
- atoms retenidos de la mesa anterior
- atoms descartados
- vacíos o faltantes detectados

### Interacciones
- click en la sección → expandir resumen detallado
- botón “ver log completo” → abrir modal

### Modal de detalle
Debería permitir leer el proceso completo, por ejemplo:

- query normalizada
- reglas aplicadas
- tags inferidos
- candidatos encontrados
- ranking o score
- retained / removed
- justificaciones

### Propósito
Esta sección sirve para:

1. evaluar el funcionamiento del sistema bibliotecario
2. hacer auditable la construcción de la mesa
3. comparar la lógica entre respuestas distintas

---

# 3. Sección “Atoms”
Representa los elementos concretos de la mesa.

## Vista compacta inicial
No mostrar el texto completo de todos los atoms.
Mostrar mejor:

- cantidad total
- agrupación por tags o roles
- lista compacta de ids o títulos
- indicadores de estado, por ejemplo:
  - exact match
  - inherited
  - support
  - contrast
  - removed

## Vistas posibles
- lista de atoms
- agrupación por tag
- agrupación por rol dentro de la mesa

## Interacciones
- click en un atom → expandir inline o abrir modal
- click en referencia `atom-...` desde la izquierda → enfocar ese atom en la derecha

## Modal de atom
Debe permitir ver:

- id
- título
- tags
- razón de inclusión
- score o criterio
- answer proyectado
- provenance
- path
- eventualmente link a fuente

---

## Persistencia y granularidad

Este sistema tiene dos granularidades de persistencia.

# A. Persistencia conversacional
Guardar por turno:

- mensaje del usuario
- respuesta del asistente
- referencia a la mesa asociada

## Ejemplo
```json
{
  "turn_id": "turn-07",
  "user_message": "...",
  "assistant_message": "...",
  "mesa_id": "mesa-07"
}
```

---

# B. Persistencia contextual
Guardar por compilación de mesa:

- mesa id
- query
- tags activos
- atom ids incluidos
- atom ids retained
- atom ids removed
- resumen de razonamiento
- referencia al log detallado

## Ejemplo
```json
{
  "mesa_id": "mesa-07",
  "query": "¿Qué dice APOS sobre encapsulación?",
  "active_tags": ["topic:encapsulation", "system:apos"],
  "retained_atom_ids": ["atom-a", "atom-b"],
  "removed_atom_ids": ["atom-x"],
  "atom_ids": ["atom-a", "atom-b", "atom-c"],
  "reasoning_summary": [
    "detected topic:encapsulation",
    "expanded to topic:process",
    "retained 2 prior atoms"
  ],
  "reasoning_log_id": "reasoning-07"
}
```

---

# C. Persistencia atómica
Cuando un atom entra en una mesa, lo importante de persistir es:

- `atom_id`
- rol en la mesa
- score o criterio
- razón de inclusión
- relación con la mesa previa

No hace falta persistir siempre el texto completo del atom.

## Principio
Persistir primero **referencias estructurales**, y resolver el contenido completo bajo demanda.

Eso hace el sistema:

- más liviano
- más auditable
- más reversible
- más alineado con SLDB

---

## Flujo ideal de uso

# Flujo 1 — Pregunta inicial
- usuario hace una pregunta
- sistema compila una mesa
- asistente responde desde esa mesa
- la respuesta queda asociada a esa mesa
- la derecha puede abrirse mostrando ese contexto

# Flujo 2 — Follow-up
- usuario hace una nueva pregunta relacionada
- sistema deriva una nueva mesa desde la anterior
- la nueva mesa muestra qué se retuvo, qué salió y qué entró
- la respuesta nueva queda asociada a esa nueva mesa

# Flujo 3 — Click en `atom-...`
- no cambia el turno conversacional
- enfoca el atom correspondiente dentro de la mesa de la derecha
- opcionalmente abre modal con su contenido completo

# Flujo 4 — Cambio de respuesta seleccionada
- cambia la mesa mostrada a la derecha
- se preserva la independencia de scroll
- el usuario puede comparar distintos momentos del razonamiento

---

## Principios UX

1. **Master-detail**
   - izquierda = timeline principal
   - derecha = inspector contextual

2. **Progressive disclosure**
   - resumen primero
   - detalle después
   - modal para largo

3. **Context is versioned**
   - cada respuesta tiene su propia mesa
   - no mezclar mesas entre turnos

4. **Structured references over raw content**
   - persistir ids y relaciones
   - resolver texto completo bajo demanda

5. **Two-tempo interface**
   - ritmo usuario: lineal, simple
   - ritmo sistema: granular, auditable

6. **Scroll independence**
   - ambas columnas deben poder recorrerse sin interferencia

---

## Criterio de éxito

La UX será correcta si permite:

- seguir la conversación con fluidez
- seleccionar cualquier respuesta previa y ver su mesa exacta
- entender por qué el sistema eligió ciertos atoms
- inspeccionar atoms sin inundar la interfaz
- diferenciar claramente conversación y razonamiento interno
- persistir conocimiento estructural por id y no solo por texto renderizado
