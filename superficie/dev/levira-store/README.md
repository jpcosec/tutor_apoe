# levira-store

Store demo SLDB del caso Levira Contigo de la maqueta "de fuentes a respuesta" (caso-0217): 3 fuentes, 30 atomos,
2 bases con 9 subgrupos (GrupoDoc), 6 tipos de relacion y 13 relaciones, el informe `salida-consulta` (4 slots),
su publicacion `salida-consulta-v1` y la respuesta `respuesta-caso-0217` con sus frases.

- `mock-data.json`: datos de la maqueta, extraidos evaluando sus constantes (`node extract-mock.cjs <app.js>`).
- `models.py` (+ `models_grupo.py`): FuenteDoc, AtomDoc, SalidaDoc, PublicacionDoc, RespuestaDoc, GrupoDoc.
- `seed.sh`: idempotente; borra y recrea `.sldb`, `docs/`, `data/` y termina con `sl edges check`.

```
bash seed.sh
PYTHONPATH=<worktree>/src:$PWD python -m sldb serve --store .sldb --pythonpath $PWD --port 8971 --cors
```

Ojo: el servidor lee el store al arrancar; tras editar con `sl fields update` hay que reiniciarlo.
El demo de la maqueta anterior sigue en `../atoms-store/`.
