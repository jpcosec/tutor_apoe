---
id: note-architecture-direction-cloud-and-knowledge-stack
title: Architecture direction for cloud, SLDB, specYaml, and deskops
tags:
- system:deskops
- system:sldb
- topic:cloud
- topic:semantics
- layer:runtime
- layer:document-model
---

# Architecture direction for cloud, SLDB, specYaml, and deskops

## Context

Working direction captured from the current discussion.

## Main points

- `specYaml/` should be treated as the canonical semantic contract.
- Structured Markdown should remain the persistent and versioned document layer.
- SLDB should be treated as the structural runtime for parsing, validation, field editing, indexing, and semantic export.
- `.sldb/` should be treated as derived state that can be regenerated.
- Deskops should remain the workflow harness for routing, recovery, gating, validation flow, and closeout.
- The preferred implementation path is local-first validation before cloud deployment.

## Local-first MVP shape

- Astro for note browsing.
- `semantic-export` to JSON for graph exploration.
- FastAPI as a thin structured API over SLDB.
- Agent tools built on SLDB operations rather than raw Markdown editing.
- Git worktrees for isolated editing sessions.

## Cloud direction

- Vercel for Astro.
- Modal for API, agent runtime, and SLDB execution.
- GitHub as canonical repo.
- Modal Volume for `.sldb/` as derived cache/state.
- Object storage such as R2 for larger binaries like PDFs.

## Open architecture implication

AntonIA's richer document flow should be considered as a migration target:

- source or decision
- anchor
- insight
- atom or downstream artifact
