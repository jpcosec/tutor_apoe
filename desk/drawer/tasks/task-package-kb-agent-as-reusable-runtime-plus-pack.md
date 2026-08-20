# Package KB agent as reusable runtime plus pack

ID: task-package-kb-agent-as-reusable-runtime-plus-pack
Status: deferred
Priority: medium

## Goal

Triage and resolve the inbox message promoted from `desk/inbox/20260820-185005-suggestion-package-kb-agent-as-reusable-runtime-plus-pack.md`.

## Scope

Refactor the APOS chat app into a reusable KB agent runtime plus a swappable knowledge pack, with APOS as the reference pack. Architecture and pack contract are formalized in docs/reusable-agent-architecture.md, docs/knowledge-pack-contract.md, and docs/diagrams/specs. Scope: extract ALIASES/EXPANSIONS/FOLLOWUP_MARKERS/scoring/default-tag from table_compiler.py, prompt policy from main.py build_prompt, atoms.json and branding into packs/<id>/, add a pack loader and KB_PACK selection, keep APOS behavior identical, then validate with a second minimal pack. Do not start code until this is promoted to an active task.

## Source

- `desk/inbox/20260820-185005-suggestion-package-kb-agent-as-reusable-runtime-plus-pack.md`

## Done When

- The message is resolved, answered, or promoted into active work.
