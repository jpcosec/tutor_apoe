# Knowledge Pack Contract

Contract for making the KB chat agent reusable across knowledge bases.

The runtime stays generic. Each knowledge base ships a **knowledge pack**.

## Boundary

- **Runtime (reusable core)**: chat app, mesa compiler engine, responder, storage, pack loader, UI.
- **Knowledge pack (per KB)**: atom inventory, config, prompt policy, expansion rules, labels.

The runtime must not hardcode domain knowledge. All domain specifics live in the pack.

## Pack layout

```
packs/<pack_id>/
  pack.json
  atoms.json
  prompt_policy.md
  expansion_rules.json
```

## pack.json

Top-level pack manifest.

```json
{
  "pack_id": "apos",
  "title": "Conversador APOS",
  "language": "es",
  "brand": {
    "app_name": "Conversador APOS",
    "subtitle": "Mesa versionada por respuesta."
  },
  "default_tags": ["system:apos"],
  "max_atoms": 5,
  "responder": {
    "model": "gemini-2.5-flash",
    "max_words": 140,
    "max_bullets": 5
  }
}
```

Required fields:

- `pack_id`
- `title`
- `language`
- `default_tags`
- `max_atoms`
- `responder.model`

## atoms.json

Atom inventory exported from the KB store.

```json
{
  "count": 90,
  "atoms": [
    {
      "id": "atom-...",
      "title": "...",
      "tags": ["system:apos", "topic:encapsulation"],
      "path": "desk/atoms/...",
      "question": "what",
      "answer": "...",
      "provenance": "..."
    }
  ]
}
```

Required atom fields:

- `id`
- `title`
- `tags`
- `path`
- `answer`

Optional atom fields:

- `question`
- `provenance`
- `relations`
- `kb_roles`

The `id` must be stable and match the `atom-...` reference convention used in answers.

## expansion_rules.json

Domain rules the compiler consumes instead of hardcoded Python dictionaries.

```json
{
  "aliases": {
    "encapsulacion": ["topic:encapsulation"],
    "esquema": ["topic:schema"]
  },
  "expansions": {
    "topic:encapsulation": ["topic:process", "topic:object", "topic:de-encapsulation"]
  },
  "followup_markers": ["ahonda", "profundiza", "eso", "sigue"],
  "scoring": {
    "exact_tag": 100,
    "expanded_tag": 30,
    "lexical_overlap": 8,
    "retained_from_previous": 18
  }
}
```

Required keys:

- `aliases`
- `expansions`
- `followup_markers`
- `scoring`

## prompt_policy.md

Responder instructions for this KB, in the pack language.

Must define:

- role framing
- evidence rules (keep `atom-...` ids)
- brevity limits
- "do not invent" rule
- insufficient-context fallback line

## What the runtime provides

Stable and pack-independent:

- FastAPI chat app and endpoints
- deterministic mesa pipeline engine
- Gemini responder wiring
- SQLite persistence (users, conversations, turns)
- turn/mesa versioning
- chat UI with left conversation sidebar and right mesa inspector

## What the pack provides

Swappable per KB:

- `atoms.json` inventory
- `pack.json` manifest and branding
- `expansion_rules.json`
- `prompt_policy.md`

## Selection contract

The runtime selects a pack by id.

```
KB_PACK=apos
KB_PACK_DIR=packs/apos
```

If unset, the runtime falls back to the bundled reference pack (`apos`).

## Migration target vs current code

Current code embeds APOS specifics inside runtime files:

- `table_compiler.py` has hardcoded `ALIASES`, `EXPANSIONS`, `FOLLOWUP_MARKERS`, scoring, and the `system:apos` default.
- `main.py` `build_prompt` embeds the Spanish APOS prompt policy.
- `atoms.json` sits inside the app directory rather than a pack directory.
- `index.html` embeds brand copy.

The refactor extracts each of these into the pack contract above without changing runtime behavior for the APOS pack.

## Non-goals

- No embedding-based RAG.
- No opaque chat memory.
- Keep every selection decision auditable through the mesa and its reasoning log.
