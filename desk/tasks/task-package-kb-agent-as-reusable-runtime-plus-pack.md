---
id: task-package-kb-agent-as-reusable-runtime-plus-pack
status: ready_for_testing
summary: ''
tags:
- workspace:desk
- artifact:task
- source:drawer
routine: routine-task-package-kb-agent-as-reusable-runtime-plus-pack
current_node: checklist-task-package-kb-agent-as-reusable-runtime-plus-pack-closeout-ready
history:
- operator-task-package-kb-agent-as-reusable-runtime-plus-pack-activate
- operator-task-package-kb-agent-as-reusable-runtime-plus-pack-ready-for-testing
references:
- desk/drawer/tasks/task-package-kb-agent-as-reusable-runtime-plus-pack.md
depends_on: []
pills:
- desk/contexts/pill-guardrail-kb-agent-packaging.md
files: []
checklists:
- checklist-task-package-kb-agent-as-reusable-runtime-plus-pack-execution-ready
- checklist-task-package-kb-agent-as-reusable-runtime-plus-pack-testing-ready
- checklist-task-package-kb-agent-as-reusable-runtime-plus-pack-closeout-ready
task_type: ''
inherits_from: []
inherit_acceptance_context: false
atoms: []
closeout_evidence_verified: false
---

# Package KB agent as reusable runtime plus pack

## Rationale

_Explain why this task exists or the business driver behind it._

Not provided.

## Goal

_Describe the concrete result this task must produce._

Triage and resolve the inbox message promoted from `desk/inbox/20260820-185005-suggestion-package-kb-agent-as-reusable-runtime-plus-pack.md`.

## Scope

_State what is in scope and what is out of scope._

Refactor the APOS chat app into a reusable KB agent runtime plus a swappable knowledge pack, with APOS as the reference pack. Architecture and pack contract are formalized in docs/reusable-agent-architecture.md, docs/knowledge-pack-contract.md, and docs/diagrams/specs. Scope: extract ALIASES/EXPANSIONS/FOLLOWUP_MARKERS/scoring/default-tag from table_compiler.py, prompt policy from main.py build_prompt, atoms.json and branding into packs/<id>/, add a pack loader and KB_PACK selection, keep APOS behavior identical, then validate with a second minimal pack. Do not start code until this is promoted to an active task.

## Implementation Path

_Outline the expected implementation route or affected surface._

Promoted from desk/drawer/tasks/task-package-kb-agent-as-reusable-runtime-plus-pack.md.

## Validation

_List the checks required before this task can close._

- pytest

## Done When

_Name the observable condition that makes the task complete._

Promoted work is completed, validated, and closed with a commit.
