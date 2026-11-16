---
subject: model <= TaskDoc
where: ''
condition: has(task_type) or nonempty(closeout_evidence)
severity: alert
moment: on_write
message: 'This task declares no closeout_evidence; it predates the field and is gated
  as code (tests, commit, atom|materialization). Declare it with: deskops edit task
  <task> closeout_evidence ''["commit", "document"]'' (kinds: tests, commit, atom, materialization,
  document, external).'
---

# Alerta de cierre: código implícito
