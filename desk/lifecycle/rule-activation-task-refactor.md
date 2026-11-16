---
subject: model <= TaskRefactorDoc
where: current_node = "ritual-execution"
condition: 'any(^subject: anchor_state = "intact" and verdict = "accepted" and kind
  = "goldens")'
severity: error
moment: on_transition
message: Una tarea task.refactor se activa, además de lo que pide task.code, con un
  recibo goldens aceptado e intacto.
---

# Activación de task.refactor
