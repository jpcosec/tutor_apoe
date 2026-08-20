# Reusable KB Agent Architecture

Formalization of the packageable chat agent before any refactor code.

Shorthand:

- **sldb = data/document layer**
- **deskops = workflow harness**

## Goal

Turn the current APOS chat app into a reusable runtime plus a swappable knowledge pack, with APOS as the reference pack.

## Layered model

1. **Document layer (sldb)**: structured Markdown atoms tracked, validated, indexed, and searchable in `.sldb`.
2. **Workflow layer (deskops)**: routing, drawer/board, rituals, gating, closeout, recovery from repo artifacts.
3. **Knowledge pack**: inventory + rules + prompt policy + branding exported from the document layer.
4. **Runtime**: FastAPI chat app, deterministic mesa compiler, Gemini responder, SQLite persistence, inspector UI.
5. **Deployment**: Modal app, Volume-backed SQLite, Vertex AI responder.

## Component view

Source spec:

- `docs/diagrams/specs/component.kb-agent-runtime.yml`

Rendered:

- `docs/diagrams/rendered/component.kb-agent-runtime.mmd`

Key point: the runtime core depends on a pack interface, not on APOS.

## Chat turn sequence

Source spec:

- `docs/diagrams/specs/sequence.chat-turn.yml`

Rendered:

- `docs/diagrams/rendered/sequence.chat-turn.mmd`

Flow: load conversation, compile mesa from previous turn, generate from `prompt_mesa`, persist turn, return versioned mesa.

## Knowledge pack pipeline

Source spec:

- `docs/diagrams/specs/component.knowledge-pack-pipeline.yml`

Rendered:

- `docs/diagrams/rendered/component.knowledge-pack-pipeline.mmd`

Flow: sources -> structured atoms -> sldb -> exporter/adapter -> `atoms.json` + config -> runtime.

## Deployment

Source spec:

- `docs/diagrams/specs/deployment.modal-runtime.yml`

Rendered:

- `docs/diagrams/rendered/deployment.modal-runtime.mmd`

## Role of sldb here

- owns atom document structure and validation
- provides retrieval via `sldb find` and `sldb docs show`
- `.sldb` is derived state that can be regenerated
- feeds the pack exporter, not the runtime directly at request time

## Role of deskops here

- governs how this reusable-agent work is routed and closed
- keeps the packaging effort in drawer/board, not chat memory
- enforces execution, testing, and closeout gates
- the knowledge pack build is a workflow-governed artifact

## What is reusable vs pack-specific

Reusable runtime:

- chat app and endpoints
- mesa pipeline engine
- Gemini responder wiring
- SQLite persistence and versioning
- inspector UI

Pack-specific:

- `atoms.json`
- `pack.json` branding and defaults
- `expansion_rules.json`
- `prompt_policy.md`

## Contract

See:

- `docs/knowledge-pack-contract.md`

## Sequencing before code

1. Formalize architecture (this document + specs). Done.
2. Define pack contract. Done.
3. Extract APOS specifics into a pack without changing behavior.
4. Add pack loader and pack selection to the runtime.
5. Validate runtime with APOS pack, then a minimal second pack.
6. Only then extend the bibliotecario population pass.

## Diagram sources

- `docs/diagrams/specs/component.kb-agent-runtime.yml`
- `docs/diagrams/specs/sequence.chat-turn.yml`
- `docs/diagrams/specs/component.knowledge-pack-pipeline.yml`
- `docs/diagrams/specs/deployment.modal-runtime.yml`
