---
name: has_model
direction: directed
cardinality: many_to_many
axis: WHAT
source_types:
- sldb_store
target_types:
- sldb_model
condition: ''
---

# has_model

## Description

The store registers this model: its own, or one it inherits from the linked store that owns it.
