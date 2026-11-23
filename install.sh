#!/usr/bin/env bash
# Instalador de Tutor APOE para macOS y Linux (en Windows, dentro de WSL).
#
#   ./install.sh            instala todo y comprueba que funciona
#   ./install.sh --check    solo comprueba una instalación existente
#
# Deja todo dentro de esta carpeta: un entorno de Python en .venv/ y las
# dependencias sldb y pron en third_party/. No pide claves ni toca nada fuera
# del repositorio. Se puede volver a ejecutar las veces que haga falta.
# Guía paso a paso: install.md
set -euo pipefail
cd "$(dirname "$0")"

MIN_MINOR=12
REPO_URL="https://storage.googleapis.com/git-repo-downloads/repo"

say() { printf '\n== %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

check_only=0
case "${1:-}" in
  "") ;;
  --check) check_only=1 ;;
  -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) die "opción desconocida: $1 (usa --check o ninguna)" ;;
esac

verify() {
  export TUTOR_EMBEDDER="${TUTOR_EMBEDDER:-hash}"
  say "Comprobando la base de conocimiento"
  .venv/bin/tutor kb validate --kb kbs/apos
  say "Probando una pregunta (modelo de prueba, sin internet ni claves)"
  .venv/bin/tutor ask --kb kbs/apos --model test "¿Qué diferencia una acción de un proceso?" | head -n 12
}

if [ "$check_only" = 1 ]; then
  [ -x .venv/bin/tutor ] || die "todavía no está instalado: ejecuta ./install.sh"
  verify
  printf '\nTodo en orden.\n'
  exit 0
fi

say "Revisando requisitos"
command -v git >/dev/null || die "falta git. Instálalo desde https://git-scm.com/downloads y vuelve a ejecutar ./install.sh"
command -v curl >/dev/null || die "falta curl. Instálalo con el gestor de paquetes del sistema y vuelve a ejecutar ./install.sh"
python=""
for candidate in python3.13 python3.12 python3 python; do
  if command -v "$candidate" >/dev/null \
     && "$candidate" -c "import sys; raise SystemExit(sys.version_info < (3, $MIN_MINOR))" 2>/dev/null; then
    python="$candidate"
    break
  fi
done
[ -n "$python" ] || die "hace falta Python 3.$MIN_MINOR o más nuevo. Instálalo desde https://www.python.org/downloads/ y vuelve a ejecutar ./install.sh"
echo "git:    $(git --version)"
echo "python: $("$python" --version) ($(command -v "$python"))"

say "Creando el entorno de Python en .venv/"
[ -x .venv/bin/python ] || "$python" -m venv .venv \
  || die "no se pudo crear .venv. En Debian/Ubuntu instala antes el paquete python3-venv"
# Activar el entorno: de aquí en adelante `python` y `pip` son los de .venv.
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip

say "Descargando sldb y pron a third_party/"
if ! command -v repo >/dev/null; then
  echo "La herramienta 'repo' no está instalada; se deja una copia en .venv/bin/"
  curl -fsSL "$REPO_URL" -o .venv/bin/repo || die "no se pudo descargar 'repo'. Revisa la conexión a internet"
  chmod +x .venv/bin/repo
fi
# `repo` pide nombre y correo de git si no están configurados. Se le da una
# identidad solo para este proceso, sin tocar la configuración de la persona.
if ! git config user.name >/dev/null || ! git config user.email >/dev/null; then
  export GIT_CONFIG_COUNT=2
  export GIT_CONFIG_KEY_0=user.name GIT_CONFIG_VALUE_0="Tutor APOE"
  export GIT_CONFIG_KEY_1=user.email GIT_CONFIG_VALUE_1="tutor-apoe@localhost"
fi
./scripts/bootstrap_deps.sh </dev/null

say "Instalando el tutor y sus paquetes (puede tardar unos minutos)"
python -m pip install --quiet -r requirements.txt

say "Construyendo la base de conocimiento (unos 2 minutos)"
export TUTOR_EMBEDDER="${TUTOR_EMBEDDER:-hash}"
tutor kb build

verify

cat <<'EOF'

Instalación lista.

Para usarlo con Codex: abre Codex en esta carpeta y pide lo que necesites con
tus palabras ("abre el visor", "qué dice la base sobre encapsulación", "carga
este PDF", "guarda los cambios").

Para usarlo a mano:
  .venv/bin/tutor web --kb kbs/apos --model test --port 8300
  y abre http://127.0.0.1:8300 en el navegador.

Las respuestas reales del tutor necesitan una clave (ver install.md, paso 4).
EOF
