# Módulo experto APOE

## Propósito

El módulo experto APOE recoge entrevistas semiestructuradas a investigadores que
conocen la teoría APOE. Su finalidad es producir evidencia atribuible y
revisable para el módulo experto; **no incorpora conocimiento directamente a
los átomos del Tutor APOE**.

El protocolo implementado es LAETEC v1.0. Conserva P01–P12, sus repreguntas y
los requisitos de conformidad, código de participante, pausa, reanudación y
validación de síntesis definidos en `knowledge/expert-apoe/protocol.json`.

## Alcance y límites

- La persona coordinadora crea una invitación por especialista.
- Cada invitación tiene un repositorio local separado para perfil,
  conversaciones, transcripciones y exportaciones.
- El entrevistador presenta solamente preguntas y repreguntas predefinidas del
  protocolo; no inventa interpretaciones ni modifica respuestas.
- Una entrevista terminada genera un Markdown exportable. Es una **fuente de
  entrevista**, no un átomo ni una propuesta aprobada.
- La incorporación al Tutor APOE requiere el proceso normal: ingesta, propuesta,
  revisión humana y aprobación explícita.

## Componentes y responsabilidades

| Componente | Ubicación | Responsabilidad |
|---|---|---|
| Visor de coordinación e entrevista | `web/expert.html`, `web/expert.js`, `web/expert.css` | Muestra el protocolo, crea invitaciones y conduce cada sesión. |
| API y persistencia | `scripts/kb.py` | Sirve el visor, controla estados, guarda turnos y produce exportaciones. |
| Protocolo | `knowledge/expert-apoe/protocol.json` | Define apertura, P01–P12, repreguntas, esquema de registro y referencia de diseño. |
| Repositorio por especialista | `knowledge/expert-apoe/experts/<id>/` | Conserva evidencia de una persona experta sin mezclarla con otras. |
| Índice del módulo | `knowledge/expert-apoe/module.json` y `README.md` | Reúne conteos y rutas de repositorios personales. |
| Compilador del Tutor APOE | `tutor compile …` | Ingiere el Markdown como fuente y propone átomos para revisión; no se ejecuta automáticamente. |

## Diagrama de componentes

```mermaid
flowchart LR
  C[Coordinación] --> V[Visor experto]
  E[Especialista] --> V
  V --> A[API en scripts/kb.py]
  A --> P[protocol.json\nLAETEC v1.0]
  A --> R[Repositorio personal\nprofile + conversaciones]
  A --> I[Índice del módulo]
  A --> X[Markdown exportable]
  X --> H[Revisión humana]
  H --> T[Compilador Tutor APOE]
  T --> Q[Átomos propuestos]
  Q --> O[Aprobación explícita]
  O --> K[KB del Tutor APOE]
```

El diagrama separa deliberadamente la entrevista de la KB. La única ruta hacia
la KB pasa por revisión humana y aprobación.

## Modelo de información

```mermaid
classDiagram
  class ExpertProtocol {
    +id: string
    +title: string
    +opening: string
    +questions: Question[12]
    +record_schema: string[]
  }
  class Question {
    +id: P01..P12
    +topic: string
    +prompt: string
    +followups: string[0..2]
  }
  class ExpertProfile {
    +id: string
    +name: string
    +created_at: datetime
    +repository: path
  }
  class Conversation {
    +id: string
    +participant_code: string
    +consent: accepted|declined
    +status: ConversationStatus
    +question_index: int
    +followups_used: int
    +coverage: map
  }
  class Turn {
    +turn: int
    +question_id: string
    +question_kind: main|followup
    +answer: string
    +coverage: complete|partial|omitted
    +related_questions: string[]
  }
  class ExportRecord {
    +markdown: file
    +synthesis_validation: object
  }
  ExpertProtocol "1" --> "12" Question
  ExpertProfile "1" --> "*" Conversation
  Conversation "1" --> "*" Turn
  Conversation "1" --> "0..1" ExportRecord
  Turn --> Question
```

Un turno puede declarar que anticipa otra pregunta, por ejemplo `P07`. Al
llegar a ella, el visor conserva el turno original y pide completar o matizar
solamente lo que falte.

## Casos de uso

| Actor | Caso de uso | Resultado |
|---|---|---|
| Coordinación | Configurar o verificar protocolo | Usa las preguntas y condiciones vigentes. |
| Coordinación | Crear invitación | Se crea `expert-<nombre>-<id>` y un enlace personal. |
| Especialista | Aceptar o declinar | Se registra la conformidad antes de formular preguntas. |
| Especialista | Responder, omitir o pedir profundización | Se guarda un turno con cobertura y, si corresponde, una repregunta. |
| Especialista | Pausar y reanudar | Se conserva la posición exacta y la siguiente pregunta. |
| Especialista | Validar síntesis o cerrar con reservas | Se registra el estado final y se habilita la exportación. |
| Equipo de investigación | Revisar e ingerir exportación | Puede proponer conocimiento nuevo, nunca publicarlo sin aprobación. |

## Secuencia de una entrevista

```mermaid
sequenceDiagram
  actor C as Coordinación
  actor E as Especialista
  participant W as Visor experto
  participant A as API
  participant R as Repositorio personal

  C->>W: Crea especialista
  W->>A: POST /api/experts
  A->>R: profile.json + conversations/index.json
  A-->>W: enlace /expert/<id>
  E->>W: Abre enlace
  W->>A: GET perfil + protocolo
  E->>W: Código participante + conformidad
  W->>A: POST /start
  A->>R: conversación con estado active
  A-->>W: P01
  loop P01 a P12, una pregunta por turno
    E->>W: Respuesta y cobertura
    W->>A: POST /responses
    A->>R: turno, cobertura y procedencia
    alt Cobertura parcial y quedan repreguntas
      A-->>W: Repregunta predefinida
    else Pregunta cubierta u omitida
      A-->>W: Siguiente pregunta
    end
  end
  A-->>W: Síntesis para validación
  E->>W: Valida, corrige o cierra con reservas
  W->>A: POST /validate
  A->>R: estado final y exportación Markdown
```

## Estados de conversación

```mermaid
stateDiagram-v2
  [*] --> created: crear repositorio
  created --> declined: declina conformidad
  created --> active: acepta + código
  active --> active: respuesta / siguiente pregunta
  active --> active: cobertura parcial / repregunta (máx. 2)
  active --> paused: pausa
  paused --> active: reanuda
  active --> awaiting_validation: P12 cubierta u omitida
  active --> closed_early: termina antes
  paused --> closed_early: termina antes
  awaiting_validation --> validated: valida síntesis
  awaiting_validation --> closed_unvalidated: cierra con reservas
  declined --> [*]
  closed_early --> [*]
  validated --> [*]
  closed_unvalidated --> [*]
```

Los estados terminales generan un archivo de exportación. `declined` no formula
preguntas.

## Pausa, cobertura y repreguntas

```mermaid
sequenceDiagram
  actor E as Especialista
  participant W as Visor
  participant A as API
  participant R as Registro

  E->>W: Respuesta a Pxx + cobertura parcial
  W->>A: POST respuesta
  A->>R: guarda turno y cobertura
  A-->>W: repregunta 1 o 2 predefinida
  E->>W: Solicita pausa
  W->>A: POST pause
  A->>R: status=paused, posición actual
  E->>W: Reanuda desde el enlace personal
  W->>A: POST resume
  A-->>W: misma pregunta pendiente
```

No se generan más de dos repreguntas por pregunta troncal. Si se registra una
cobertura parcial sin una repregunta disponible, el visor avanza y conserva la
cobertura como parcial.

## Repositorio personal y trazabilidad

Cada especialista vive en una carpeta independiente:

```text
knowledge/expert-apoe/experts/expert-<nombre>-<id>/
├── profile.json
├── conversations/
│   ├── index.json
│   ├── conversation-<id>.json
│   └── conversation-<id>.md
└── exports/
    └── conversation-<id>.md
```

El JSON mantiene el estado operativo; la transcripción Markdown ofrece lectura
humana; el exportable añade metadatos de conformidad, estado, protocolo,
respuestas y validación. Por tanto, una interpretación puede remitirse al
código de participante, identificador de pregunta y turno.

## Del cierre a la KB del Tutor APOE

```mermaid
sequenceDiagram
  actor R as Revisor/a
  participant E as Exportación Markdown
  participant C as Compilador Tutor APOE
  participant P as Propuestas
  participant K as KB aprobada

  R->>E: Descarga registro final
  R->>C: Ingresa el archivo como fuente
  C->>P: Propone átomos trazables
  R->>P: Revisa, corrige o rechaza
  R->>K: Aprueba únicamente los átomos aceptados
```

Con el CLI disponible, el flujo operativo es:

```bash
# Copiar el archivo descargado a una carpeta de fuentes del proyecto.
tutor compile ingest sources/entrevistas/<archivo>.md --kb kbs/apos --title "Entrevista experta APOE"

# Pedir propuestas, pero no escribirlas todavía.
tutor compile run "criterios operativos extraídos de entrevista experta APOE" --kb kbs/apos --max 5 --dry-run
```

Después se revisan las propuestas y se aprueban individualmente con el flujo
descrito en `docs/compiler.md`. Las transcripciones pueden contener opiniones,
ambigüedades o desacuerdos; estos se conservan como evidencia atribuida y no
se convierten por sí mismos en afirmaciones de la KB.

## Interfaz y rutas

| Ruta | Uso |
|---|---|
| `/expert` | Coordinación: protocolo, invitaciones e índice de especialistas. |
| `/expert/<id>` | Sesión de la persona especialista. |
| `POST /api/experts` | Crea perfil y enlace. |
| `POST /api/experts/<id>/start` | Registra conformidad y código. |
| `POST /api/experts/<id>/responses` | Registra un turno y su cobertura. |
| `POST /api/experts/<id>/pause` y `/resume` | Controla continuidad de sesión. |
| `POST /api/experts/<id>/validate` | Cierra y genera la exportación. |
| `GET /api/experts/<id>/export?conversation=<id>` | Descarga el Markdown exportable. |

## Restricciones de despliegue y privacidad

La instalación actual se sirve en `127.0.0.1`; sus enlaces funcionan solo en
esta máquina. Antes de invitar a personas externas se necesita un despliegue
con URL compartida, autenticación, política de tratamiento de datos y copias
de seguridad acordes con el equipo de investigación. La interfaz actual no
incluye autenticación ni una política de anonimización automática.

## Verificación realizada

Se verificaron en una entrevista simulada y aislada:

- aceptación y declinación de conformidad;
- presentación de P01 y registro de código;
- cobertura parcial y repregunta predefinida;
- pausa y reanudación en la pregunta pendiente;
- referencia a un turno que anticipa una pregunta posterior;
- cierre temprano, validación y generación de Markdown exportable;
- sintaxis de Python, JavaScript y consistencia del diff.

No se usaron las respuestas de una entrevista real durante estas pruebas.
