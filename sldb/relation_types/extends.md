---
name: extends
direction: directed
cardinality: many_to_many
axis: WHAT
source_types:
- sldb_model
target_types:
- sldb_model
condition: ''
---

# extends

## Description

The model inherits from that model (base_models); instances of the source are instances of the target.
