#!/usr/bin/env bash
# El agente conversacional del tutor (submódulo agent/ = conversational-agent-arch).
#
#   ./agent.sh kb       regenera la KB del agente desde desk/atoms
#   ./agent.sh run      KB + servidor local en http://127.0.0.1:8000
#   ./agent.sh deploy   KB + deploy a Modal (URL pública)
#
# `run` necesita el runtime instalado (ver agent/docs/TUTOR-APOE.md) y un
# .env en agent/ con GOOGLE_API_KEY + GOOGLE_GENAI_USE_VERTEXAI=true.
# `deploy` solo necesita python, git y una cuenta de Modal.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
AGENT="$ROOT/agent"

usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

ensure_agent() {
  [ -f "$AGENT/app.py" ] || git -C "$ROOT" submodule update --init agent
}

build_kb() {
  (cd "$AGENT" && python3 -m scripts.import_tutor_apoe --tutor-root "$ROOT")
}

case "${1:-}" in
  kb)
    ensure_agent
    build_kb
    ;;
  run)
    ensure_agent
    build_kb
    TUTOR_APOE_ROOT="$ROOT" exec "$AGENT/scripts/run_tutor_apoe.sh"
    ;;
  deploy)
    ensure_agent
    # La KB se regenera solo si el runtime está instalado; si no, se deploya
    # la que trae el submódulo (generada desde estos mismos átomos).
    if (cd "$AGENT" && python3 -c 'import sldb, kb_agent') 2>/dev/null; then
      build_kb
    else
      echo "runtime no instalado: se deploya la KB versionada en agent/knowledge_apoe"
    fi
    APP_DIR="$AGENT" exec bash "$AGENT/scripts/deploy_tutor_apoe.sh"
    ;;
  *)
    usage
    ;;
esac
