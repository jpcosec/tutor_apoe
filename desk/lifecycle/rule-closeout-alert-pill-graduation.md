---
subject: model <= TaskDoc
where: ''
condition: 'not nonempty(pills) or any(references: model <= AtomDoc)'
severity: alert
moment: on_write
message: A task that binds pills graduates them into an atom; reference the atom it
  graduated to.
---

# Alerta de cierre: graduación de pills
