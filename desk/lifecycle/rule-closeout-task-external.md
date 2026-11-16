---
subject: model <= TaskExternalDoc
where: current_node = "ritual-closeout"
condition: 'any(^subject: kind = "evidence" and fact = "external" and anchor_state
  = "intact" and verdict = "accepted")'
severity: error
moment: on_transition
message: Una tarea task.external se cierra con un recibo evidence aceptado e intacto
  de external (lo escribe deskops closeout verify).
---

# Cierre de task.external
