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

step "wiki de configuración: la interfaz compilada y una lectura por el proxy"
tutor web --kb kbs/apos --model test --port 8300 >/tmp/tutor-web.log 2>&1 &
web_pid=$!
trap 'kill "$web_pid" 2>/dev/null || true' EXIT
for _ in $(seq 60); do curl -fs http://127.0.0.1:8300/api/health >/dev/null && break; sleep 1; done
curl -fsS http://127.0.0.1:8300/wiki/ | grep -q '/wiki/assets/' || { cat /tmp/tutor-web.log; echo "la wiki no sirvió su interfaz"; exit 1; }
curl -fsS "http://127.0.0.1:8300/api/wiki/document/segments?id=agent-tutor-apos" \
  | python -c "import json,sys; d=json.load(sys.stdin); assert d['model']=='AgentDoc' and d['payload']['framing'], d; print('AgentDoc leído por el proxy:', d['payload']['title'])"
kill "$web_pid"; wait "$web_pid" 2>/dev/null || true
trap - EXIT

step "MCP: autoprueba de tools (crear KB, poblar, consultar, correr turno)"
tutor-mcp --selftest

step "tests"
python -m pytest tests/tutor runtime -q -p no:cacheprovider

printf '\nSMOKE OK\n'
