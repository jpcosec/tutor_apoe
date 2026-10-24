---
name: applies_to_source
direction: directed
cardinality: many_to_many
axis: WHAT
source_types:
- relation_type
target_types:
- sldb_model
condition: ''
---

# applies_to_source

## Description

Instances of this model may be the source of edges of this relation type: the verbs a class can be subject of.
