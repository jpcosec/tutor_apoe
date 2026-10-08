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
  persona.md
  expansion_rules.json
  index.html
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

### relations (optional)

Explicit typed edges to other atoms, used later by the extended bibliotecario for multi-hop expansion. The current runtime does not require it.

```json
"relations": [
  { "type": "leads_to", "target": "atom-..." },
  { "type": "contrasts_with", "target": "atom-..." },
  { "type": "prerequisite_of", "target": "atom-..." }
]
```

- `type`: free string, but recommended vocabulary: `leads_to`, `prerequisite_of`, `contrasts_with`, `example_of`, `part_of`, `supports`.
- `target`: an existing atom `id` in the same inventory.
- Unknown `type` values are tolerated and ignored by the current runtime.

### kb_roles (optional)

Declares what role an atom tends to play in a contexto conversacional. Advisory only for the current runtime; the extended bibliotecario will use it for support-role balancing.

```json
"kb_roles": ["definition", "mechanism"]
```

Recommended vocabulary:

- `definition`
- `difficulty`
- `mechanism`
- `pedagogy`
- `example`
- `context`

Multiple roles allowed. Unknown roles are tolerated and ignored now.

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
KB_PACK=apos            # pack id; must equal packs/<KB_PACK>/pack.json pack_id
KB_PACK_DIR=packs       # base dir holding pack folders (optional)
```

Resolution rules:

- Effective pack directory is `${KB_PACK_DIR:-packs}/${KB_PACK}`.
- `pack.json` `pack_id` must equal the directory name; mismatch is a load error.
- If `KB_PACK` is unset, the runtime falls back to the bundled reference pack (`apos`).
- A missing or malformed pack (bad `pack.json`, unreadable `atoms.json`) fails fast at startup with a clear error, not at request time.

## Incoming-KB assumption (this iteration)

For now the runtime assumes each new KB arrives as a **ready atoms inventory** (already distilled) that satisfies this contract. Producing `atoms.json` from raw sources / `.sldb` export is intentionally out of scope for this iteration and is tracked as a separate future concern. See `docs/reusable-agent-architecture.md` (Deferred / annotated for later).

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
