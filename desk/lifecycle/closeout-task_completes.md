---
source_id: RitualDoc:ritual-closeout
target_id: RitualDoc:ritual-closeout
relation_type: task_completes
condition: status = "ready_for_testing"
attributes:
  sets:
    status: closed
  terminal: true
---

# Task completes

## Notes

The task is ready for closeout; its type's closeout rule (`rule-closeout-<type>`) holds it back until `deskops closeout verify` has written the evidence receipts it asks for, accepted and intact. Then it closes.
