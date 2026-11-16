---
subject: model <= TaskDebugDoc
where: current_node = "ritual-closeout"
condition: 'any(^subject: kind = "evidence" and fact = "tests" and anchor_state =
  "intact" and verdict = "accepted") and any(^subject: kind = "evidence" and fact
  = "commit" and anchor_state = "intact" and verdict = "accepted") and (any(^subject:
  kind = "evidence" and fact = "atom" and anchor_state = "intact" and verdict = "accepted")
  or any(^subject: kind = "evidence" and fact = "materialization" and anchor_state
  = "intact" and verdict = "accepted"))'
severity: error
moment: on_transition
message: Una tarea task.debug se cierra con recibos evidence aceptados e intactos
  de tests, commit y atom o materialization (los escribe deskops closeout verify).
---

# Cierre de task.debug
