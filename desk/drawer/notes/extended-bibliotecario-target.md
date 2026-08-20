---
id: note-extended-bibliotecario-target
title: Target shape for the extended bibliotecario version
tags:
- system:deskops
- system:sldb
- topic:retrieval
- topic:mesa
- topic:atoms
- topic:chat
- layer:workflow
- layer:runtime
---

# Target shape for the extended bibliotecario version

## Context

Direction captured from the current chat about the richer retrieval path we want to recover and strengthen.

Scope decision: this is deferred. The current iteration only packages the runtime + APOS pack and validates against a second ready-made atoms KB. The extended bibliotecario below is a later task.

Core future goal: replace the fixed `max_atoms` cap with a bibliotecario that decides which atoms stay and which leave per turn, instead of a hard top-k.

## What the current version already has

- Deterministic mesa compilation from local atom inventory.
- `include_tags`, `expanded_tags`, scoring, and per-turn mesa persistence.
- `retained_atom_ids`, `added_atom_ids`, `removed_atom_ids`.
- A response generated from `prompt_mesa` rather than raw free-form chat memory.
- UI inspection of the mesa attached to each answer.

## What the extended bibliotecario version should aim for

- The bibliotecario should not stop at a shallow tag match.
- It should actively **populate the mesa** by pulling a broader but still auditable working set of atoms before the final answer.
- The population pass should be explicit and inspectable, not hidden inside the responder.

## Target behavior

- Start from the user query.
- Infer initial tags and topic anchors.
- Pull first-pass atoms by exact topic and structural cues.
- Expand to nearby atoms that clarify prerequisites, contrasts, mechanisms, examples, or consequences.
- Keep prior-turn atoms when they still support continuity.
- Add new atoms when the query shifts or deepens.
- Remove atoms that no longer support the current question.
- Hand the responder a mesa that is richer than the minimal top-k but still bounded and inspectable.

## Retrieval qualities to aim for

- Better follow-up handling than simple lexical overlap.
- Stronger multi-hop expansion across APOS relations such as:
  - action -> process -> object -> schema
  - interiorization -> encapsulation -> de-encapsulation -> totality
  - theory -> pedagogy -> example domain
- Explicit support atoms for:
  - definitions
  - difficulties
  - mechanisms
  - pedagogical implications
  - domain examples
- Preference for structural retrieval from SLDB-backed artifacts over embedding-style RAG.

## Desired mesa-building phases

1. Query interpretation.
2. Initial atom selection.
3. Expansion pass.
4. Continuity pass from previous mesa.
5. Pruning pass.
6. Final responder-facing mesa projection.

## Evidence we should preserve per phase

- Why each atom entered.
- Whether it came from exact tag, expansion rule, continuity, or contrast.
- Which prior atoms were retained and why.
- Which atoms were removed and why.
- Which expansion edges or heuristics fired.

## Practical target delta vs current implementation

- Increase the sophistication of the population pass.
- Make expansion rules richer and more domain-aware.
- Preserve more explicit provenance for each inclusion decision.
- Distinguish support roles inside the mesa, not only score order.
- Let the bibliotecario assemble a more complete context package before Gemini writes the answer.

## Non-goal

- Do not turn this into opaque autonomous memory.
- Keep the system auditable through repo artifacts and persisted mesa state.
