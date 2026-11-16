---
subject: model <= TaskRefactorDoc
where: current_node = "ritual-closeout"
condition: 'any(^subject: kind = "goldens" and anchor_state = "intact" and verdict
  = "accepted")'
severity: error
moment: on_transition
message: Una tarea task.refactor se cierra, además de lo que pide task.code, con un
  recibo goldens aceptado e intacto (deskops review record --kind goldens).
---

# Cierre de task.refactor
