/**
 * Prueba de aceptación contra los datos reales del store demo de Levira (dev/levira-store):
 * las consultas de cada slot de `salida-consulta`, resueltas con `matchQuery`, no dejan más
 * "nuevos" que p4 (slot reglas) y cada slot cuadra con lo que muestra la maqueta.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { atomsFromDocuments, matchQuery } from "./atoms";
import { parseQuery } from "./atom-report";
import type { Edge, GraphDocument } from "./contract";

const DIR = resolve(__dirname, "../../dev/levira-store");
const M = JSON.parse(readFileSync(resolve(DIR, "mock-data.json"), "utf-8"));
const norm = (s: string) => s.normalize("NFD").replace(/\p{Mn}/gu, "").toLowerCase();

const baseOf: Record<string, string> = {};
for (const b of M.bases) for (const g of b.groups) baseOf[g] = b.id;
const docs: GraphDocument[] = M.atomos.map((a: any) => ({
  id: a.id,
  model_name: "AtomDoc",
  path: `docs/atoms/${a.id}.md`,
  payload: { kind: a.type, status: a.status, source: "FuenteDoc:x", start: 0, end: 1, tags: a.tags.map((t: string) => `${norm(baseOf[t]!)}.${norm(t)}`), text: a.text, quote: "q", conf: a.conf },
}));
const atoms = atomsFromDocuments(docs);
const edges: Edge[] = M.relaciones.map((r: any) => {
  const ref = (x: string) => (x.startsWith("g:") ? `GrupoDoc:${norm(baseOf[x.slice(2)]!)}-${norm(x.slice(2))}` : `AtomDoc:${x}`);
  return { id: r.id, source: ref(r.source), target: ref(r.target), type: r.type.replace(/ /g, "_"), origin: "relation", relationDoc: r.id };
});
// Misma traducción que dev/levira-store/seed.sh (`query(sec)`): tokens de los chips + descripción.
const queryOf = (sec: any): string =>
  [
    ...sec.filters.map(([k, v]: [string, string]) =>
      k === "Base" ? `base:${norm(v)}` : k === "Distancia" ? `distancia:${/\d+/.exec(v)![0]}` : k === "Tag" ? `tag:${norm(v)}` : `relacion:${v.split(",").map((x) => norm(x).trim().replace(/ /g, "_")).join(",")}`,
    ),
    sec.query,
  ].join(" ");
// Exclusiones extra de seed.sh (la lista de s1 en la maqueta no sale de sus filtros).
const extra = JSON.parse(/EXCLUIDOS_EXTRA = (\{.*\})/.exec(readFileSync(resolve(DIR, "seed.sh"), "utf-8"))![1]!.replace(/'/g, '"')) as Record<string, string>;
const path = (id: string) => `docs/atoms/${id}.md`;

const SLOT: Record<string, string> = { s1: "respuesta", s2: "acceso", s3: "cercanos", s4: "reglas" };
const rows = M.informe.sections.map((sec: any) => {
  const items: [string, string][] = sec.items;
  const lista = items.filter(([, e]) => e === "regla" || e === "pin").map(([a]) => path(a));
  const pins = items.filter(([, e]) => e === "pin").map(([a]) => path(a));
  const excluidos = [...items.filter(([, e]) => e === "excluido").map(([a]) => path(a)), ...(extra[sec.id] ?? "").split(" ").filter(Boolean).map(path)];
  const known = new Set([...lista, ...pins, ...excluidos]);
  const pool = atoms.filter((a) => a.status !== "descartado");
  const result = matchQuery(pool, parseQuery(queryOf(sec)).filters, edges).map((a) => a.path);
  return { slot: SLOT[sec.id]!, sec, lista, excluidos, result, nuevos: result.filter((p) => !known.has(p)) };
});
const slot = (name: string) => rows.find((r: any) => r.slot === name)!;

describe("consultas del store demo de Levira", () => {
  it("en total hay exactamente 1 nuevo: p4, en el slot reglas", () => {
    expect(rows.flatMap((r: any) => r.nuevos.map((p: string) => `${r.slot}:${p}`))).toEqual(["reglas:docs/atoms/p4.md"]);
  });
  it("respuesta: 16 en lista; la consulta trae 22 (paciente + asistente + vecinos a 1 salto, f7 por la relación de p2 sobre el grupo red) y los 8 que la maqueta no muestra están excluidos", () => {
    const r = slot("respuesta");
    expect(r.lista).toHaveLength(16);
    expect(r.result).toHaveLength(22);
    expect(r.result.filter((p: string) => !r.lista.includes(p)).sort()).toEqual(["c2", "c6", "f7", "p1", "p2", "p3", "p4", "p6"].map(path).sort());
    expect(r.nuevos).toEqual([]);
  });
  it("acceso: fB, f4, f3", () => {
    expect(slot("acceso").result.sort()).toEqual(["f3", "f4", "fB"].map(path).sort());
    expect(slot("acceso").lista).toHaveLength(3);
  });
  it("cercanos: f5 y f6 en lista, f7 excluido", () => {
    expect(slot("cercanos").result.sort()).toEqual(["f5", "f6"].map(path));
    expect(slot("cercanos").lista).toHaveLength(2);
    expect(slot("cercanos").excluidos).toEqual([path("f7")]);
  });
  it("reglas: 5 en lista, p6 excluido y p4 nuevo", () => {
    const r = slot("reglas");
    expect(r.lista).toHaveLength(5);
    expect(r.excluidos).toEqual([path("p6")]);
    expect(r.nuevos).toEqual([path("p4")]);
    expect(r.result).toHaveLength(7);
  });
});
