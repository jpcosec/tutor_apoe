---
name: child_of
direction: directed
cardinality: many_to_one
axis: WHAT
source_types:
- KnowledgeAtom
- BranchNode
target_types:
- BranchNode
condition: ''
---

# child_of

## Description

El origen es un hijo del destino en la taxonomía APOS: un átomo cuelga de una rama, una rama de otra rama. Proyección tipada del `parent_id` de los átomos fuente.
