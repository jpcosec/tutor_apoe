---
subject: model <= TaskDocsDoc
where: current_node = "ritual-closeout"
condition: 'any(^subject: kind = "evidence" and fact = "commit" and anchor_state =
  "intact" and verdict = "accepted") and any(^subject: kind = "evidence" and fact
  = "document" and anchor_state = "intact" and verdict = "accepted")'
severity: error
moment: on_transition
message: Una tarea task.docs se cierra con recibos evidence aceptados e intactos de
  commit y document (los escribe deskops closeout verify).
---

# Cierre de task.docs
