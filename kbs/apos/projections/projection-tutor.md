---
name: tutor
stores:
- local
models:
- KnowledgeAtom
- BranchNode
relations:
- name: child_of
  mode: read
actions: []
aliases: []
naming: {}
display: {}
key: {}
matching:
  neighbors: 3
  threshold: 0.55
exposed: false
mutability: 0
---

# tutor

Lo que ve el rol tutor: todos los átomos de conocimiento (KnowledgeAtom y SourceAtom) y la taxonomía (BranchNode) con sus aristas child_of, en solo lectura.
