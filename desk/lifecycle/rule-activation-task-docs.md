---
subject: model <= TaskDocsDoc
where: current_node = "ritual-execution"
condition: 'any(^subject: anchor_state = "intact" and verdict = "accepted" and kind
  = "preflight") and all(depends_on: status = "closed")'
severity: error
moment: on_transition
message: Una tarea task.docs se activa con un recibo preflight aceptado e intacto
  y sus dependencias cerradas.
---

# Activación de task.docs
