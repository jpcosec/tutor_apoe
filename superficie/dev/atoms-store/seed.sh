#!/usr/bin/env bash
# Store demo de atomos: acta + 12 atomos + 7 tipos de relacion + 9 relaciones + informe por slots.
# Idempotente: borra y recrea .sldb, docs/ y data/. Usa el sldb de este worktree.
# Uso: bash seed.sh   (desde cualquier lado)
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
export PYTHONPATH="$HERE/../../../src:$HERE"
rm -rf .sldb docs data
mkdir -p docs/atoms docs/relations docs/relation-types data
S="--store .sldb --pythonpath ."
sl() { python -m sldb "$@"; }

python - <<'P'
import json, yaml
D = json.loads(r"""{
 "paras": [
  "Acta de la reunión de arquitectura del 14 de septiembre. Asistieron Camila, Tomás y Rodrigo.",
  "Se revisó el estado de la ingesta. El proceso actual lee los PDF desde un bucket y los procesa en lote cada noche, lo que genera un retraso de hasta 24 horas en la disponibilidad de los documentos.",
  "Se decidió reemplazar el lote nocturno por una cola de eventos, de modo que cada documento se procese al llegar. Tomás queda a cargo de la migración y estima tenerla lista para fin de octubre.",
  "Para el almacenamiento, el equipo acordó mantener Postgres y agregar la extensión pgvector en lugar de sumar una base vectorial aparte. Camila advirtió que el volumen de embeddings podría duplicarse si se indexan también los anexos.",
  "Queda pendiente definir quién revisa la calidad de la extracción. Rodrigo propuso que el equipo de datos haga un muestreo semanal, pero no hubo acuerdo.",
  "Riesgo principal: si la cola se satura en los cierres de mes, los documentos podrían volver a acumularse."
 ],
 "atoms": [
  {
   "id": "a1",
   "kind": "hecho",
   "text": "La ingesta actual procesa los PDF en lote cada noche",
   "tags": [
    "infra.ingesta"
   ],
   "p": 1,
   "quote": "El proceso actual lee los PDF desde un bucket y los procesa en lote cada noche",
   "conf": 0.93,
   "status": "confirmado",
   "start": 129,
   "end": 207
  },
  {
   "id": "a2",
   "kind": "hecho",
   "text": "El lote nocturno retrasa hasta 24 h la disponibilidad de documentos",
   "tags": [
    "infra.ingesta"
   ],
   "p": 1,
   "quote": "lo que genera un retraso de hasta 24 horas en la disponibilidad de los documentos",
   "conf": 0.88,
   "status": "propuesto",
   "start": 209,
   "end": 290
  },
  {
   "id": "a3",
   "kind": "decision",
   "text": "Reemplazar el lote nocturno por una cola de eventos",
   "tags": [
    "infra.ingesta"
   ],
   "p": 2,
   "quote": "Se decidió reemplazar el lote nocturno por una cola de eventos",
   "conf": 0.96,
   "status": "confirmado",
   "start": 293,
   "end": 355
  },
  {
   "id": "a4",
   "kind": "hecho",
   "text": "Tomás lidera la migración a la cola",
   "tags": [
    "equipo",
    "infra.ingesta"
   ],
   "p": 2,
   "quote": "Tomás queda a cargo de la migración",
   "conf": 0.81,
   "status": "propuesto",
   "start": 406,
   "end": 441
  },
  {
   "id": "a5",
   "kind": "hecho",
   "text": "Migración estimada para fin de octubre",
   "tags": [
    "infra.ingesta"
   ],
   "p": 2,
   "quote": "estima tenerla lista para fin de octubre",
   "conf": 0.64,
   "status": "propuesto",
   "start": 444,
   "end": 484
  },
  {
   "id": "a6",
   "kind": "decision",
   "text": "Mantener Postgres y usar pgvector para los embeddings",
   "tags": [
    "infra.almacenamiento"
   ],
   "p": 3,
   "quote": "el equipo acordó mantener Postgres y agregar la extensión pgvector",
   "conf": 0.91,
   "status": "confirmado",
   "start": 511,
   "end": 577
  },
  {
   "id": "a7",
   "kind": "riesgo",
   "text": "Indexar anexos podría duplicar el volumen de embeddings",
   "tags": [
    "infra.almacenamiento",
    "riesgos"
   ],
   "p": 3,
   "quote": "el volumen de embeddings podría duplicarse si se indexan también los anexos",
   "conf": 0.72,
   "status": "propuesto",
   "start": 643,
   "end": 718
  },
  {
   "id": "a8",
   "kind": "pendiente",
   "text": "Falta definir quién revisa la calidad de extracción",
   "tags": [
    "equipo"
   ],
   "p": 4,
   "quote": "Queda pendiente definir quién revisa la calidad de la extracción",
   "conf": 0.86,
   "status": "propuesto",
   "start": 721,
   "end": 785
  },
  {
   "id": "a9",
   "kind": "pendiente",
   "text": "Propuesta: muestreo semanal a cargo del equipo de datos",
   "tags": [
    "equipo"
   ],
   "p": 4,
   "quote": "Rodrigo propuso que el equipo de datos haga un muestreo semanal",
   "conf": 0.47,
   "status": "propuesto",
   "start": 787,
   "end": 850
  },
  {
   "id": "a10",
   "kind": "riesgo",
   "text": "La cola podría saturarse en los cierres de mes",
   "tags": [
    "riesgos",
    "infra.ingesta"
   ],
   "p": 5,
   "quote": "si la cola se satura en los cierres de mes",
   "conf": 0.79,
   "status": "propuesto",
   "start": 893,
   "end": 935
  },
  {
   "id": "a11",
   "kind": "entidad",
   "text": "Cola de eventos",
   "tags": [
    "infra.ingesta"
   ],
   "p": 2,
   "quote": "cola de eventos",
   "conf": 0.9,
   "status": "propuesto",
   "start": 340,
   "end": 355
  },
  {
   "id": "a12",
   "kind": "entidad",
   "text": "Postgres",
   "tags": [
    "infra.almacenamiento"
   ],
   "p": 3,
   "quote": "Postgres",
   "conf": 0.95,
   "status": "propuesto",
   "start": 537,
   "end": 545
  }
 ]
}""")
paras, atoms = D["paras"], D["atoms"]
body = "\n\n".join(paras)
dump = lambda obj, path: yaml.safe_dump(obj, open(path, "w"), allow_unicode=True, sort_keys=False)
dump({"title": "Acta de arquitectura 2026-09-14", "body": body}, "data/acta.yaml")
for a in atoms:
    assert body[a["start"]:a["end"]] == a["quote"], a["id"]
    dump({"kind": a["kind"], "status": a["status"], "source": "ActaDoc:acta-2026-09-14", "source_field": "body",
          "start": a["start"], "end": a["end"], "conf": a["conf"], "tags": a["tags"], "text": a["text"], "quote": a["quote"]},
         f"data/{a['id']}.yaml")
TYPES = {"motiva": "El origen explica la razon del destino.", "responsable_de": "Responde por el destino.",
         "plazo_de": "Fija el plazo del destino.", "menciona": "El origen nombra al destino.",
         "afecta": "El origen afecta al destino.", "propone_solucion_a": "El origen propone resolver el destino.",
         "condiciona": "El origen condiciona al destino."}
for n, desc in TYPES.items():
    dump({"title": n, "name": n, "direction": "directed", "cardinality": "many_to_many", "axis": "WHY",
          "source_types": ["AtomDoc"], "target_types": ["AtomDoc"], "condition": "", "description": desc}, f"data/rt-{n}.yaml")
RELS = [("r1", "a2", "a3", "motiva"), ("r2", "a1", "a2", "motiva"), ("r3", "a4", "a3", "responsable_de"),
        ("r4", "a5", "a3", "plazo_de"), ("r5", "a3", "a11", "menciona"), ("r6", "a10", "a11", "afecta"),
        ("r7", "a7", "a6", "afecta"), ("r8", "a6", "a12", "menciona"), ("r9", "a9", "a8", "propone_solucion_a")]
for n, s, t, ty in RELS:
    dump({"title": n, "source_id": f"AtomDoc:{s}", "target_id": f"AtomDoc:{t}", "relation_type": ty, "condition": "", "notes": ""}, f"data/{n}.yaml")
path = lambda a: f"docs/atoms/{a}.md"
SLOTS = {  # slot: (query, modo, lista, pins, excluidos)
    "resumen": ("tipo:hecho tag:infra.ingesta", "prosa", ["a1", "a2", "a5"], [], []),
    "decisiones": ("tipo:decision tag:infra", "viñetas", ["a3", "a6", "a4"], ["a4"], []),
    "riesgos": ("tipo:riesgo", "tabla", ["a7"], [], []),
    "pendientes": ("tipo:pendiente", "viñetas", ["a8"], [], ["a9"]),
}
inf = {"title": "Informe de avance: migracion de ingesta"}
for s, (q, modo, lista, pins, exc) in SLOTS.items():
    inf.update({s: [path(a) for a in lista], f"{s}_query": q, f"{s}_pins": [path(a) for a in pins],
                f"{s}_excluidos": [path(a) for a in exc], f"{s}_modo": modo})
dump(inf, "data/informe.yaml")
P

sl stores init --path . >/dev/null
for m in ActaDoc AtomDoc InformeAvanceDoc; do sl models add models:$m $S >/dev/null; done
sl edges init $S >/dev/null
sl docs create --model ActaDoc -o docs/acta-2026-09-14.md data/acta.yaml $S >/dev/null
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do sl docs create --model AtomDoc -o docs/atoms/a$i.md data/a$i.yaml $S >/dev/null; done
for n in motiva responsable_de plazo_de menciona afecta propone_solucion_a condiciona; do
  sl docs create --model RelationTypeDoc -o docs/relation-types/$n.md data/rt-$n.yaml $S >/dev/null; done
for i in 1 2 3 4 5 6 7 8 9; do sl docs create --model RelationDoc -o docs/relations/r$i.md data/r$i.yaml $S >/dev/null; done
sl docs create --model InformeAvanceDoc -o docs/informe-avance.md data/informe.yaml $S >/dev/null
# Extensiones: cada seed.d/*.sh registra sus propios modelos y datos (usa $S y sl); asi varias
# piezas pueden agregar al store demo sin editar este archivo.
for ext in "$HERE"/seed.d/*.sh; do [ -e "$ext" ] && . "$ext"; done
sl edges rebuild --store .sldb >/dev/null
sl edges check --store .sldb
echo "store listo en $HERE/.sldb"
