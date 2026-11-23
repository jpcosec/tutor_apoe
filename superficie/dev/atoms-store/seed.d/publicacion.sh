# Publicacion previa del informe demo: informe-avance-v1 (foto inmutable, PublicacionDoc).
# Las secciones salen del mismo renderizador que usa GET /render (sldb render -> render_model_markdown),
# partidas por heading igual que hace la UI (publicationPayload).
sl models add models_publicacion:PublicacionDoc $S >/dev/null
sl render models:InformeAvanceDoc data/informe.yaml data/informe-render.md --pythonpath . >/dev/null
python - <<'P'
import re, yaml
md = open("data/informe-render.md", encoding="utf-8").read()
md = re.sub(r"^---\n.*?\n---\n+", "", md, count=1, flags=re.S)
parts = re.split(r"^## (.+)$", md, flags=re.M)  # [preambulo, label, texto, label, texto, ...]
by = {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts), 2)}
inf = yaml.safe_load(open("data/informe.yaml", encoding="utf-8"))
atoms = []
for s in ("resumen", "decisiones", "riesgos", "pendientes"):
    atoms += [a for a in inf[s] if a not in atoms]
doc = {"informe": "informe-avance", "version": 1, "atoms": atoms, "title": inf["title"]}
for label, slot in (("Resumen", "resumen"), ("Decisiones", "decisiones"), ("Riesgos", "riesgos"), ("Pendientes", "pendientes")):
    doc[slot] = by[label]
yaml.safe_dump(doc, open("data/pub-informe-avance-v1.yaml", "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
P
sl docs create --model PublicacionDoc -o docs/informe-avance-v1.md data/pub-informe-avance-v1.yaml $S >/dev/null
