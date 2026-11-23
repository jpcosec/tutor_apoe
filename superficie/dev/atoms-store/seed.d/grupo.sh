# Grupos como documentos (GrupoDoc): una relacion sobre un grupo la heredan sus atomos.
# Slug = tag con los puntos cambiados por guiones (infra.ingesta -> infra-ingesta).
sl models add models_grupo:GrupoDoc $S >/dev/null
mkdir -p docs/grupos
python - <<'P'
import yaml
dump = lambda obj, path: yaml.safe_dump(obj, open(path, "w"), allow_unicode=True, sort_keys=False)
dump({"title": "Riesgos", "tag": "riesgos", "description": "Todo lo que puede salir mal."}, "data/g-riesgos.yaml")
dump({"title": "r10", "source_id": "GrupoDoc:riesgos", "target_id": "AtomDoc:a5", "relation_type": "condiciona",
      "condition": "", "notes": "Relacion sobre el grupo: la heredan los atomos del grupo riesgos."}, "data/r10.yaml")
P
sl docs create --model GrupoDoc -o docs/grupos/riesgos.md data/g-riesgos.yaml $S >/dev/null
# Tipos que admiten un grupo como extremo (ademas de AtomDoc):
#   ambos extremos: condiciona, afecta, menciona, motiva, propone_solucion_a
#   solo origen:    responsable_de (un grupo responde por algo)
#   solo destino:   plazo_de (un plazo aplica a todos los atomos del grupo)
grp_type() { # nombre source_types target_types (JSON)
  sl fields update docs/RelationTypeDoc/$1/source_types "$2" $S >/dev/null
  sl fields update docs/RelationTypeDoc/$1/target_types "$3" $S >/dev/null
}
BOTH='["AtomDoc","GrupoDoc"]'
for n in condiciona afecta menciona motiva propone_solucion_a; do grp_type $n "$BOTH" "$BOTH"; done
grp_type responsable_de "$BOTH" '["AtomDoc"]'
grp_type plazo_de '["AtomDoc"]' "$BOTH"
sl docs create --model RelationDoc -o docs/relations/r10.md data/r10.yaml $S >/dev/null
