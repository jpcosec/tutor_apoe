---
subject: model <= TaskCodeDoc
where: current_node = "ritual-execution"
condition: 'any(^subject: anchor_state = "intact" and verdict = "accepted" and kind
  = "preflight") and any(^subject: anchor_state = "intact" and verdict = "accepted"
  and kind = "bundle") and all(depends_on: status = "closed")'
severity: error
moment: on_transition
message: Una tarea task.code se activa con recibos preflight y bundle aceptados e
  intactos y sus dependencias cerradas.
---

# Activación de task.code
