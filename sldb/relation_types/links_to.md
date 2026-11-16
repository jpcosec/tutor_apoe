---
name: links_to
direction: directed
cardinality: many_to_many
axis: WHERE
source_types:
- sldb_store
target_types:
- sldb_store
condition: ''
---

# links_to

## Description

The store links that store under an alias (`stores add`): it reads its documents and inherits its models.
