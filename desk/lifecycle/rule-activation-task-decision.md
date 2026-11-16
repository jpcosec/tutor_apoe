---
subject: model <= TaskDecisionDoc
where: current_node = "ritual-execution"
condition: 'any(^subject: anchor_state = "intact" and verdict = "accepted" and kind
  = "owner") and all(depends_on: status = "closed")'
severity: error
moment: on_transition
message: Una tarea task.decision se activa con un recibo owner aceptado e intacto
  y sus dependencias cerradas.
---

# Activación de task.decision
