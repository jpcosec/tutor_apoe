---
# runtime-xxx
id: runtime-pi-deepseek-flash
# draft | active | archived
status: active
# Runtime binary identifier matching RoleDoc.kind values, e.g. pi, claude, codex
kind: pi
binary: pi
# Empty means this runtime does not support that capability
model_flag: --model
fallback_models_flag: ''
# comma | space | repeat
fallback_models_join: comma
tools_flag: ''
# comma | space | repeat
tools_join: comma
system_prompt_flag: --system-prompt
# inline | file
system_prompt_delivery: inline
# Optional fixed system prompt text; empty means role-provided
system_prompt: 'Revisor barato aislado de un encargo de planificación. Trabajas solo
  con el input explícito: sin herramientas, historial ni otras fuentes. No ejecutas
  nada. Responde en español con estas secciones exactas: REFORMULACION (propósito,
  resultado, repo, límites), AMBIGUEDADES (numeradas, cada una con cita textual del
  input y qué obligaría a inventar; escribe "ninguna" si no hay), DRY-RUN (lecturas,
  cambios previstos, dependencias y validaciones futuras, sin ejecutar), FUTURO (lo
  que produce otro nodo o decide un humano, no ambigüedad). REFORMULACION describe
  el encargo del nodo, no esta revisión. DRY-RUN describe cómo lo ejecutaría un ejecutor
  futuro, hipotéticamente y sin ejecutar nada. Si el nodo es un agregado o paquete
  no ejecutable, dilo y además recorre cómo lo cumplen sus hijos, qué transfiere cada
  uno al siguiente y cómo se valida el resultado conjunto. Máximo 350 palabras.'
session_flag: ''
extra_args:
- --provider
- deepseek
- --model
- deepseek-flash
- --thinking
- low
- --offline
- --no-session
- --no-context-files
- --no-skills
- --no-extensions
- --no-prompt-templates
- --no-tools
- --print
# RoleDoc fields this runtime cannot honor
unsupported_role_fields: []
# e.g. system:deskops
tags:
- system:deskops
---

# Pi deepseek-flash isolated reviewer

## Summary

_Summarize what this runtime is and when to use it._

Isolated cheap reviewer profile (pi deepseek-flash) used by `deskops review`.

## Notes

_Operational notes such as authentication requirements or version pins._

Verified cheap profile for ritual-context-review step 3 (D4): offline, no session/context/skills/extensions/prompt-templates/tools.
