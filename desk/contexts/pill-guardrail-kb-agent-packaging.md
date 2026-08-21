---
# pill-xxx
id: pill-guardrail-kb-agent-packaging
# e.g., language:python, library:pydantic
tags: []
---

# Guardrail: KB agent packaging

## What

_Define the context or guardrail this pill carries._

Runtime reusable en apps/kb_agent/runtime/; packs en apps/kb_agent/packs/<id>/. APOS es pack de referencia con comportamiento identico.

## Why

_Explain why this context matters for safe execution._

Evitar acoplar el runtime a APOS y permitir multiples KBs aisladas.

## When

_Describe when an agent should apply this pill._

Durante todo el refactor de empaquetado y al levantar una segunda KB (Vitali).

## Where

_Name the files, surfaces, or scope this pill applies to._

apps/kb_agent/runtime, apps/kb_agent/packs/<id>, instancias con su propia DB.

## How

_Describe the correct way to apply this guidance._

Extraer ALIASES/EXPANSIONS/FOLLOWUP_MARKERS/scoring/default-tag y prompt policy a config del pack; pack loader + KB_PACK/KB_PACK_DIR; cada instancia con su atoms.json, su SQLite DB y su branding.

## How Not

_Describe the shortcut or failure mode to avoid._

No hardcodear APOS ni rutas globales; no compartir una DB unica entre packs; no incluir el bibliotecario extendido; no cambiar comportamiento del pack APOS.
