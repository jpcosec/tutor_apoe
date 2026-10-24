#!/usr/bin/env bash
# Trae sldb y pron a third_party/ con Google `repo` y los instala en modo editable.
# Variables: MANIFEST_URL (por defecto, el remoto de este repo), MANIFEST_BRANCH.
set -euo pipefail
cd "$(dirname "$0")/../third_party"
url="${MANIFEST_URL:-https://github.com/jpcosec/tutor_apoe.git}"
branch="${MANIFEST_BRANCH:-main}"
[ -d .repo ] || repo init -u "$url" -b "$branch" -m third_party/manifest.xml --depth=1 --no-repo-verify
repo sync -j2
python -m pip install -e sldb -e pron
