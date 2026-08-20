---
id: board-001
scope: desk
tasks: []
pills:
- desk/contexts/pills.md
rituals:
- desk/rituals/execution.md
- desk/rituals/testing.md
- desk/rituals/closeout.md
tags:
- workspace:desk
---

# Tutor APOE Board

## Purpose

Route the active execution set for Tutor APOE.

## Notes

Bootstrap complete. Add active task docs under `desk/tasks/` and route them here.

## Current architecture direction

- Canonical semantic contract should live in `specYaml/`.
- Structured Markdown should remain the persistent document layer.
- SLDB should be treated as structural runtime and derived index, not semantic canon.
- Deskops should remain the workflow harness.
- The preferred path is local-first validation before cloud deployment.
