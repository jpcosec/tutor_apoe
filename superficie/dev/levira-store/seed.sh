#!/usr/bin/env bash
# Store demo del caso Levira Contigo (maqueta "de fuentes a respuesta"): 3 fuentes, 30 atomos, 2 bases y
# 9 subgrupos, 6 tipos de relacion + 13 relaciones, informe de 4 slots, publicacion v1 y la respuesta.
# Todo sale de mock-data.json (regenerable con: node extract-mock.cjs <app.js de la maqueta>).
# Idempotente: borra y recrea .sldb, docs/ y data/. Usa el sldb de este worktree.
# Uso: bash seed.sh   (desde cualquier lado)
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
export PYTHONPATH="$HERE/../../../src:$HERE"
rm -rf .sldb docs data
mkdir -p docs/fuentes docs/atoms docs/relations docs/relation-types docs/grupos data
S="--store .sldb --pythonpath ."
sl() { python -m sldb "$@"; }

python - <<'P'
import json, re, unicodedata, yaml
M = json.load(open("mock-data.json", encoding="utf-8"))
dump = lambda obj, path: yaml.safe_dump(obj, open(path, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False, width=10**6)
norm = lambda s: "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()

# ---- fuentes
FUENTE = {"prompt": ("system-prompt", "Programa"), "folleto": ("folleto", "Programa"), "paciente": ("mensaje-paciente", "Paciente")}
bodies, starts = {}, {}   # id maqueta -> body ; indice de parrafo -> (fuente, offset)
for f in M["fuentes"]:
    name, base = FUENTE[f["id"]]
    off = 0
    for i in f["paras"]:
        starts[i] = (f["id"], off)
        off += len(M["parrafos"][i]) + 2
    body = "\n\n".join(M["parrafos"][i] for i in f["paras"])
    bodies[f["id"]] = body
    dump({"title": f["title"], "tipo": f["id"] if f["id"] != "paciente" else "mensaje", "base": base,
          "descripcion": M["fuenteDescripcion"][f["id"]], "body": body}, f"data/fuente-{name}.yaml")

# ---- atomos (tags = base.subgrupo sin tildes y en minuscula)
base_of = {g: b["id"] for b in M["bases"] for g in b["groups"]}
tag_of = lambda g: f"{norm(base_of[g])}.{norm(g)}"
cnt = {}
for a in M["atomos"]:
    para, quote = a["anchor"]
    fid, off = starts[para]
    body = bodies[fid]
    start = off + M["parrafos"][para].index(quote)
    end = start + len(quote)
    assert body[start:end] == quote, a["id"]
    assert body.index(quote) == start or body.count(quote) > 1, a["id"]
    cnt[fid] = cnt.get(fid, 0) + 1
    dump({"kind": a["type"], "status": a["status"], "source": f"FuenteDoc:{FUENTE[fid][0]}", "source_field": "body",
          "start": start, "end": end, "tags": [tag_of(t) for t in a["tags"]], "text": a["text"], "quote": quote, "conf": a["conf"]},
         f"data/{a['id']}.yaml")
    assert len(a["tags"]) == 1
print("atomos por fuente:", cnt, "total", len(M["atomos"]))

# ---- grupos: 2 bases + 9 subgrupos
grupos = []
for b in M["bases"]:
    grupos.append((norm(b["id"]), b["id"], norm(b["id"]), f"Base {b['id']}: reune todos sus subgrupos."))
    for g in b["groups"]:
        tag = f"{norm(b['id'])}.{norm(g)}"
        grupos.append((tag.replace(".", "-"), g, tag, f"Subgrupo {g} de la base {b['id']}."))
for slug, title, tag, desc in grupos:
    dump({"title": title, "tag": tag, "description": desc}, f"data/g-{slug}.yaml")
open("data/grupos.txt", "w").write("\n".join(g[0] for g in grupos))

# ---- tipos de relacion y relaciones
RT = {"cumple": ("CONDITION", "El origen cumple lo que pide el destino.", False),
      "activa": ("WHY", "El origen activa el destino: hace que aplique.", False),
      "consulta_por": ("ABOUT", "El origen pregunta por el destino.", False),
      "cerca_de": ("LOCATION", "El origen esta geograficamente cerca del destino.", False),
      "detalla": ("DETAIL", "El origen da el detalle del destino.", False),
      "restringe": ("CONSTRAINT", "El origen restringe al destino (y a lo que este agrupa).", True)}
assert [n.replace("_", " ") for n in RT] == M["tiposRelacion"]
for n, (axis, desc, grp) in RT.items():
    ends = ["AtomDoc", "GrupoDoc"] if grp else ["AtomDoc"]
    dump({"title": n, "name": n, "direction": "directed", "cardinality": "many_to_many", "axis": axis,
          "source_types": ends, "target_types": ends, "condition": "", "description": desc}, f"data/rt-{n}.yaml")
ref = lambda x: f"GrupoDoc:{norm(base_of[x[2:]]) + '-' + norm(x[2:])}" if x.startswith("g:") else f"AtomDoc:{x}"
for r in M["relaciones"]:
    note = "Relacion sobre el grupo: la heredan los atomos del grupo." if r.get("inherited") else ""
    dump({"title": r["id"], "source_id": ref(r["source"]), "target_id": ref(r["target"]),
          "relation_type": r["type"].replace(" ", "_"), "condition": "", "notes": note}, f"data/{r['id']}.yaml")

# ---- informe (SalidaDoc)
path = lambda a: f"docs/atoms/{a}.md"
SLOT = {"s1": "respuesta", "s2": "acceso", "s3": "cercanos", "s4": "reglas"}
def query(sec):
    toks = []
    for k, v in sec["filters"]:
        if k == "Base": toks.append("base:" + norm(v))
        elif k == "Distancia": toks.append("distancia:" + re.match(r"\d+", v).group())
        elif k == "Tag": toks.append("tag:" + norm(v))
        elif k == "Relación": toks.append("relacion:" + ",".join(norm(x).strip().replace(" ", "_") for x in v.split(",")))
        else: raise SystemExit("filtro desconocido " + k)
    return " ".join(toks + [sec["query"]])
# La lista de la maqueta en s1 (16 atomos) no sale de sus filtros: `base:paciente tag:asistente` (union de
# grupos) + `distancia:1` devuelve 22 atomos (f7 entra por la relacion de p2 sobre el grupo red). Los que la maqueta no muestra quedan EXCLUIDOS a mano (no cuentan
# como "nuevos"), asi el unico nuevo sin revisar es p4 en el slot reglas. core/levira-query.test.ts lee esta linea.
EXCLUIDOS_EXTRA = {"s1": "c2 c6 p1 p2 p3 p4 p6 f7"}
inf = {"title": M["informe"]["title"]}
for sec in M["informe"]["sections"]:
    s = SLOT[sec["id"]]
    est = dict(sec["items"])
    inf.update({s: [path(a) for a, e in sec["items"] if e in ("regla", "pin")], f"{s}_titulo": sec["title"],
                f"{s}_rotulo": sec["slot"], f"{s}_query": query(sec), f"{s}_modo": sec["mode"],
                f"{s}_pins": [path(a) for a, e in sec["items"] if e == "pin"],
                f"{s}_excluidos": [path(a) for a, e in sec["items"] if e == "excluido"] + [path(a) for a in EXCLUIDOS_EXTRA.get(sec["id"], "").split()]})
dump(inf, "data/salida.yaml")

# ---- respuesta
fr = M["frases"]["s1"]
dump({"title": "Respuesta al paciente", "caso": "caso-0217", "proyecto": "levira-contigo", "estado": "borrador",
      "generada_por": "modelo (borrador de demostración)", "slot": "respuesta", "mensaje": "mensaje-paciente",
      "respuesta": " ".join(f["text"] for f in fr), "frases": [{"texto": f["text"], "atomos": f["from"]} for f in fr]},
     "data/respuesta.yaml")
P

sl stores init --path . >/dev/null
sl models add models:FuenteDoc $S >/dev/null
sl models add models:AtomDoc $S >/dev/null
sl models add models:SalidaDoc $S >/dev/null
sl models add models_grupo:GrupoDoc $S >/dev/null
sl models add models:PublicacionDoc $S >/dev/null
sl models add models:RespuestaDoc $S >/dev/null
sl edges init $S >/dev/null
for n in system-prompt folleto mensaje-paciente; do
  sl docs create --model FuenteDoc -o docs/fuentes/$n.md data/fuente-$n.yaml $S >/dev/null; done
for f in data/*.yaml; do
  b=$(basename $f .yaml)
  case $b in
    fuente-*|rt-*|g-*|r[0-9]*|salida|respuesta) ;;
    *) sl docs create --model AtomDoc -o docs/atoms/$b.md $f $S >/dev/null ;;
  esac
done
for f in data/g-*.yaml; do b=$(basename $f .yaml); b=${b#g-}
  sl docs create --model GrupoDoc -o docs/grupos/$b.md $f $S >/dev/null; done
for f in data/rt-*.yaml; do b=$(basename $f .yaml); b=${b#rt-}
  sl docs create --model RelationTypeDoc -o docs/relation-types/$b.md $f $S >/dev/null; done
for f in data/r[0-9]*.yaml; do b=$(basename $f .yaml)
  sl docs create --model RelationDoc -o docs/relations/$b.md $f $S >/dev/null; done
sl docs create --model SalidaDoc -o docs/salida-consulta.md data/salida.yaml $S >/dev/null
sl docs create --model RespuestaDoc -o docs/respuesta-caso-0217.md data/respuesta.yaml $S >/dev/null

# Publicacion previa (v1) del informe: foto inmutable. Las secciones salen del mismo renderizador que GET /render,
# partidas por heading igual que hace la UI.
sl render models:SalidaDoc data/salida.yaml data/salida-render.md --pythonpath . >/dev/null
python - <<'P'
import re, yaml
md = open("data/salida-render.md", encoding="utf-8").read()
md = re.sub(r"^---\n.*?\n---\n+", "", md, count=1, flags=re.S)
parts = re.split(r"^## (.+)$", md, flags=re.M)
by = {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts), 2)}
inf = yaml.safe_load(open("data/salida.yaml", encoding="utf-8"))
atoms = []
doc = {"informe": "salida-consulta", "version": 1, "atoms": [], "title": inf["title"]}
for s in ("respuesta", "acceso", "cercanos", "reglas"):
    atoms += [a for a in inf[s] if a not in atoms]
    doc[s] = by[inf[s + "_titulo"]]
doc["atoms"] = atoms
yaml.safe_dump(doc, open("data/pub-v1.yaml", "w", encoding="utf-8"), allow_unicode=True, sort_keys=False, width=10**6)
P
sl docs create --model PublicacionDoc -o docs/salida-consulta-v1.md data/pub-v1.yaml $S >/dev/null
sl edges rebuild --store .sldb >/dev/null
sl edges check --store .sldb
echo "store listo en $HERE/.sldb"
