#!/usr/bin/env bash
# Smoke test del instalador aislado (ver docker/Dockerfile).
# Sin red ni credenciales: HashEmbedder + modelo de prueba de pydantic-ai.
set -euo pipefail
cd "$(dirname "$0")/.."
export TUTOR_EMBEDDER="${TUTOR_EMBEDDER:-hash}"

step() { printf '\n== %s\n' "$*"; }

step "deps externas presentes"
python -c "import sldb, pron; print('sldb', sldb.__file__); print('pron', pron.__file__)"

step "paquetes vendoreados importan"
python -c "import ontology, cognitive, kb, embeddings, llm, agents, tools, semantics, context, tutor; print('ok')"

step "KB de APOS: build idempotente + validación"
python -m tutor.kb_build --atoms desk/atoms --out kbs/apos
tutor kb validate --kb kbs/apos

step "retrieval sobre la KB"
tutor kb rank --kb kbs/apos "qué es la encapsulación en APOS" --k 5

step "turno de tutor con modelo de prueba (sin LLM real)"
tutor ask --kb kbs/apos --model test "¿Qué diferencia una acción de un proceso?"

step "MCP: autoprueba de tools (crear KB, poblar, consultar, correr turno)"
tutor-mcp --selftest

step "tests"
python -m pytest tests/tutor runtime -q -p no:cacheprovider

printf '\nSMOKE OK\n'
