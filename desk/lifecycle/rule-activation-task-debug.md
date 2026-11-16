---
subject: model <= TaskDebugDoc
where: current_node = "ritual-execution"
condition: 'any(^subject: anchor_state = "intact" and verdict = "accepted" and kind
  = "preflight") and any(^subject: anchor_state = "intact" and verdict = "accepted"
  and kind = "reproduction") and all(depends_on: status = "closed")'
severity: error
moment: on_transition
message: Una tarea task.debug se activa con recibos preflight y reproduction aceptados
  e intactos y sus dependencias cerradas.
---

# Activación de task.debug
