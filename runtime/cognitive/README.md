# cognitive (contrato canónico)

Paquete neutral de DTOs y Protocols del modelo canónico. Depende solo de `pydantic`
y `antonia-ontology` (Ref, canonical_json). No importa SQL, SLDB, Pydantic AI ni clientes.

## Contenido

| Módulo | Qué declara |
|---|---|
| `jsons` | `JsonValue`, `JsonObject`, `JsonArray` (JSON recursivo) |
| `scope` | `Scope`, `AccessScope` |
| `errors` | errores de dominio del contrato canónico |
| `events` | `Event`, `Observation`, `ExternalReceipt` |
| `guards` | `GuardExpr`, `GuardEvidence` |
| `machine` | `MachineDefinition`, `MachineInstance`, `TransitionDecision`, `MachineCommand`, `TimerSpec` |
| `repository` | puertos neutrales `MachineRepository`, `MachineTimerRepository`, `WorldEvidenceRepository` |
| `coordination` | `CoordinationRuleDoc`, `DeliveryReport`, `Coordinator` |
| `actions` | `ImplementationBinding`, `ActionInvocation`, `ActionResult`, `ActionExecutionStore`, `ActionExecutor` |
| `review` | `ReviewRequest`, `ReviewResolution`, `ReviewRequestStore` |
| `actors` | `SelfAssignment`, `ActorBinding`, `ActorResult`, `ActorRuntime`, `SelfAssignmentStore` |
| `goals` | `GoalInstance`, `GoalEvidence`, `GoalAssessment`, `GoalStore` |
| `process` | `ProcessInstance`, `ProcessStore` |
| `knowledge` | `KnowledgeVersion`, `KnowledgeActivation`, `KnowledgeSelector`, `KnowledgeStore` |
| `world` | `DataCommand`, `EntitySchema`, `WorldData`, `WorldExternal`, `ExternalAdapter` |
| `context` | `ContextSnapshot`, `SnapshotBuilder`, `ContextProjector` |

Importar siempre la raíz pública `cognitive`; consumidores externos no importan submódulos.

## Tests

`make test M=runtime/cognitive` después de registro en uv/workspace (supervisor).