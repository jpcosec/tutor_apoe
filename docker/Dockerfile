# Instalador aislado de tutor_apoe.
# Prueba que el repo es autocontenido: sldb y pron entran por google `repo`
# desde el manifest versionado, el resto por pip. Sin llaves SSH ni modelos
# descargados: el smoke test usa HashEmbedder y el modelo de prueba de pydantic-ai.
#
#   docker build -f docker/Dockerfile -t tutor-apoe .
#   docker run --rm tutor-apoe                     # corre scripts/docker_smoke.sh
#   docker run --rm -it tutor-apoe bash            # inspeccionar

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 TUTOR_EMBEDDER=hash

RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL https://storage.googleapis.com/git-repo-downloads/repo -o /usr/local/bin/repo \
 && chmod a+rx /usr/local/bin/repo \
 && git config --global user.email docker@tutor-apoe.local \
 && git config --global user.name tutor-apoe \
 && git config --global color.ui false

WORKDIR /app

# 1. Dependencias externas por manifest. Solo se copia el manifest para que
#    esta capa se cachee mientras no cambie.
COPY third_party/manifest.xml /tmp/manifest/manifest.xml
RUN git -C /tmp/manifest init -q -b main \
 && git -C /tmp/manifest add manifest.xml \
 && git -C /tmp/manifest commit -qm "manifest" \
 && mkdir -p third_party && cd third_party \
 && repo init -q -u /tmp/manifest -b main -m manifest.xml --depth=1 --no-repo-verify \
 && repo sync -q -j2 \
 && rm -rf .repo

# 2. El workspace: paquetes vendoreados + paquete tutor, todo editable.
COPY requirements.txt pyproject.toml ./
COPY runtime ./runtime
COPY src ./src
RUN pip install -q -r requirements.txt

# 3. Datos: la KB de APOS y la fuente de los átomos.
COPY kbs ./kbs
COPY desk/atoms ./desk/atoms
COPY scripts ./scripts
COPY tests ./tests
COPY benchmarks ./benchmarks
# Reglas léxicas del runtime viejo: baseline `heuristic` del benchmark.
COPY apps/kb_agent/packs/apos ./apps/kb_agent/packs/apos

CMD ["bash", "scripts/docker_smoke.sh"]
