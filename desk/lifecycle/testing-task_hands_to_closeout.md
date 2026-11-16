---
source_id: RitualDoc:ritual-testing
target_id: RitualDoc:ritual-closeout
relation_type: task_hands_to_closeout
condition: nonempty(validation)
attributes:
  sets:
    status: ready_for_testing
  terminal: false
---

# Task hands to closeout

## Notes

The task has validation to prove and moves to the closeout ritual.
