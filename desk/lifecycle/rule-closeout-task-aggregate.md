---
subject: model <= TaskAggregateDoc
where: current_node = "ritual-closeout"
condition: 'any(^subject: kind = "evidence" and fact = "commit" and anchor_state =
  "intact" and verdict = "accepted")'
severity: error
moment: on_transition
message: Una tarea task.aggregate se cierra con un recibo evidence aceptado e intacto
  de commit (lo escribe deskops closeout verify).
---

# Cierre de task.aggregate
