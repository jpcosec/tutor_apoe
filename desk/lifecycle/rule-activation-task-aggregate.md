---
subject: model <= TaskAggregateDoc
where: current_node = "ritual-execution"
condition: 'all(depends_on: status = "closed")'
severity: error
moment: on_transition
message: Una tarea task.aggregate se activa con sus dependencias cerradas.
---

# Activación de task.aggregate
