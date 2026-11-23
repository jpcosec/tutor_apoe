import { describe, expect, it } from "vitest";
import fixture from "./__fixtures__/atoms.json";
import {
  acceptAtom,
  actasFromDocuments,
  anchorState,
  atomsFromDocuments,
  excludeAtom,
  groupEndpoints,
  groupTree,
  informesFromDocuments,
  inheritedEdges,
  matchQuery,
  nextAtomName,
  pinAtom,
  refreshSlot,
  relationTypesFromDocuments,
  repairAnchor,
  selectionToAtomPayload,
  unpinAtom,
  validRelationTypes,
  validRelationTypesBetween,
} from "./atoms";
import type { Edge, GraphDocument, InformeSlot } from "./contract";

const docs = fixture.documents as unknown as GraphDocument[];
const edges = fixture.edges as Edge[];
const atoms = atomsFromDocuments(docs);
const acta = actasFromDocuments(docs)[0]!;
const atom = (id: string) => atoms.find((a) => a.id === id)!;

describe("lectura de documentos", () => {
  it("lee átomos, actas, tipos e informes por modelo", () => {
    expect(atoms.map((a) => a.id)).toEqual(["a1", "a2", "a3", "a4", "a5", "a6"]);
    expect(atom("a3")).toMatchObject({ gid: "AtomDoc:a3", path: "docs/atoms/a3.md", kind: "hecho", status: "propuesto", source: "ActaDoc:acta" });
    expect(acta).toMatchObject({ id: "acta", gid: "ActaDoc:acta", title: "Acta 14/09" });
    expect(relationTypesFromDocuments(docs).map((t) => t.name)).toEqual(["motiva", "cubre"]);
    const inf = informesFromDocuments(docs)[0]!;
    expect(inf.slots.decisiones).toEqual({ atomos: ["docs/atoms/a2.md"], query: "kind:decision", pins: ["docs/atoms/a2.md"], excluidos: [], modo: "viñetas" });
    expect(inf.slots.resumen.modo).toBe("prosa");
    expect(inf.slots.pendientes).toMatchObject({ atomos: [], query: "", modo: "viñetas" });
  });

  it("el tipo desconocido se conserva; el estado fuera de enum cae a propuesto", () => {
    const [a] = atomsFromDocuments([{ id: "x", model_name: "AtomDoc", path: "p", payload: { kind: "??", status: "??" } } as GraphDocument]);
    expect(a).toMatchObject({ kind: "??", status: "propuesto", conf: 1, source_field: "body" });
  });
});

describe("anchorState / repairAnchor", () => {
  it("intact: el tramo coincide", () => {
    expect(anchorState(acta.body, atom("a2"))).toEqual({ state: "intact" });
    expect(repairAnchor(acta.body, atom("a2"))).toBeNull();
  });
  it("drifted: la cita está en otro sitio; se repara", () => {
    const check = anchorState(acta.body, atom("a3"));
    expect(check.state).toBe("drifted");
    expect(check.movedTo).toBe(atom("a3").start - 7);
    const fix = repairAnchor(acta.body, atom("a3"))!;
    expect(acta.body.slice(fix.start, fix.end)).toBe(atom("a3").quote);
  });
  it("orphan: la cita ya no está", () => {
    expect(anchorState(acta.body, atom("a4"))).toEqual({ state: "orphan" });
    expect(repairAnchor(acta.body, atom("a4"))).toBeNull();
  });
  it("con la cita repetida elige la ocurrencia más cercana al start", () => {
    const body = "ab ab ab";
    expect(anchorState(body, { start: 4, end: 6, quote: "xx" }).state).toBe("orphan");
    expect(anchorState(body, { start: 4, end: 5, quote: "ab" })).toEqual({ state: "drifted", movedTo: 3 });
  });
  it("una cita vacía es huérfana", () => {
    expect(anchorState("abc", { start: 0, end: 0, quote: "" }).state).toBe("orphan");
  });
});

describe("groupTree", () => {
  const tree = groupTree(atoms);
  const find = (id: string) => {
    const walk = (nodes: typeof tree): (typeof tree)[number] | undefined =>
      nodes.reduce<(typeof tree)[number] | undefined>((hit, n) => hit ?? (n.id === id ? n : walk(n.children)), undefined);
    return walk(tree);
  };
  it("arma la jerarquía por puntos y cuenta átomos distintos por rama", () => {
    expect(tree.map((g) => g.id)).toEqual(["arquitectura", "infra", "reuniones"]);
    const infra = find("infra")!;
    expect(infra.count).toBe(5);
    expect(infra.atomIds).toEqual(["a5"]);
    expect(infra.children.map((c) => c.id)).toEqual(["infra.ingesta", "infra.proveedores"]);
    expect(find("infra.ingesta")).toMatchObject({ name: "ingesta", count: 2, atomIds: ["a2", "a3"] });
    expect(find("infra.proveedores")!.count).toBe(2);
  });
  it("un átomo puede estar en varios grupos", () => {
    expect(find("arquitectura")!.atomIds).toEqual(["a2"]);
    expect(find("infra.ingesta")!.atomIds).toContain("a2");
  });
});

describe("validRelationTypes", () => {
  const types = relationTypesFromDocuments(docs);
  it("solo ofrece tipos que nombran AtomDoc en ambos extremos", () => {
    expect(validRelationTypes(types, atom("a3"), atom("a2")).map((t) => t.name)).toEqual(["motiva"]);
    const structural = [{ ...types[0]!, name: "references", source_types: [], target_types: [] }];
    expect(validRelationTypes(structural, atom("a3"), atom("a2"))).toEqual([]);
    const other = [{ ...types[0]!, name: "has_model", source_types: ["sldb_store"], target_types: ["sldb_model"] }];
    expect(validRelationTypes(other, atom("a3"), atom("a2"))).toEqual([]);
  });
  it("no ofrece un tipo si ya existe la misma arista, ni relaciona un átomo consigo mismo", () => {
    expect(validRelationTypes(types, atom("a5"), atom("a2"), edges)).toEqual([]);
    expect(validRelationTypes(types, atom("a2"), atom("a5"), edges).map((t) => t.name)).toEqual(["motiva"]);
    expect(validRelationTypes(types, atom("a2"), atom("a2"))).toEqual([]);
  });
});

describe("inheritedEdges", () => {
  it("proyecta las aristas del grupo sobre sus átomos, incluidos subgrupos", () => {
    const out = inheritedEdges(edges, "infra", atoms);
    expect(out.map((e) => e.atomId)).toEqual(["a2", "a3", "a4", "a5", "a6"]);
    expect(out.every((e) => e.inherited && e.via === "infra" && e.edge.id === "e3" && e.target === "AtomDoc:a2")).toBe(true);
    expect(out[0]!.source).toBe("AtomDoc:a2");
  });
  it("un grupo sin aristas propias no hereda nada", () => {
    expect(inheritedEdges(edges, "infra.ingesta", atoms)).toEqual([]);
  });
  it("reconoce GrupoDoc:<slug> como extremo de grupo (origen o destino) y conserva los formatos viejos", () => {
    expect(groupEndpoints("infra.ingesta")).toEqual(expect.arrayContaining(["GrupoDoc:infra-ingesta", "infra.ingesta", "semantic_tag/infra.ingesta"]));
    const asSource: Edge = { id: "g1", source: "GrupoDoc:infra", target: "AtomDoc:a1", type: "afecta", origin: "relation_doc", relationDoc: "r10" };
    const out = inheritedEdges([asSource], "infra", atoms);
    expect(out.map((e) => e.atomId)).toEqual(["a2", "a3", "a4", "a5", "a6"]); // subgrupos incluidos
    expect(out.every((e) => e.source === e.atomGid && e.target === "AtomDoc:a1" && e.via === "infra")).toBe(true);
    const asTarget: Edge = { id: "g2", source: "AtomDoc:a1", target: "GrupoDoc:infra-ingesta", type: "afecta", origin: "relation_doc", relationDoc: "r11" };
    const inh = inheritedEdges([asTarget], "infra.ingesta", atoms);
    expect(inh.length).toBeGreaterThan(0);
    expect(inh.every((e) => e.source === "AtomDoc:a1" && e.target === e.atomGid)).toBe(true);
    // el slug de un grupo no toca a otro
    expect(inheritedEdges([asTarget], "infra.almacenamiento", atoms)).toEqual([]);
  });
});

describe("slots de informe", () => {
  const slot: InformeSlot = { atomos: ["p1", "p2"], query: "", pins: ["p2"], excluidos: ["p9"], modo: "viñetas" };
  it("refreshSlot: nuevos excluye lista, pins y excluidos; salieron ignora pins", () => {
    expect(refreshSlot(slot, ["p1", "p3", "p9", "p3", "p4"])).toEqual({ nuevos: ["p3", "p4"], salieron: [] });
    expect(refreshSlot(slot, ["p3"])).toEqual({ nuevos: ["p3"], salieron: ["p1"] });
  });
  it("nada entra a la lista hasta aceptarlo", () => {
    const r = refreshSlot(slot, ["p3"]);
    expect(slot.atomos).not.toContain("p3");
    const next = acceptAtom(slot, r.nuevos[0]!);
    expect(next.atomos).toEqual(["p1", "p2", "p3"]);
    expect(refreshSlot(next, ["p3"]).nuevos).toEqual([]);
  });
  it("excluir saca de lista y pins y sobrevive al refresco; pin sobrevive", () => {
    const ex = excludeAtom(slot, "p2");
    expect(ex).toMatchObject({ atomos: ["p1"], pins: [], excluidos: ["p9", "p2"] });
    expect(refreshSlot(ex, ["p2"]).nuevos).toEqual([]);
    const pinned = pinAtom(slot, "p5");
    expect(pinned).toMatchObject({ atomos: ["p1", "p2", "p5"], pins: ["p2", "p5"] });
    expect(refreshSlot(pinned, []).salieron).toEqual(["p1"]);
    expect(unpinAtom(pinned, "p5")).toMatchObject({ pins: ["p2"], atomos: ["p1", "p2", "p5"] });
  });
  it("accept/pin sobre un excluido lo reincorpora; no duplica", () => {
    expect(acceptAtom(slot, "p9").excluidos).toEqual([]);
    expect(pinAtom(slot, "p2").pins).toEqual(["p2"]);
    expect(acceptAtom(slot, "p1").atomos).toEqual(["p1", "p2"]);
  });
});

describe("matchQuery", () => {
  it("filtra por kind, status, tag (prefijo de grupo) y texto", () => {
    expect(matchQuery(atoms, { kind: "riesgo" }).map((a) => a.id)).toEqual(["a4"]);
    expect(matchQuery(atoms, { kind: ["riesgo", "decision"] }).map((a) => a.id)).toEqual(["a2", "a4"]);
    expect(matchQuery(atoms, { status: "descartado" }).map((a) => a.id)).toEqual(["a6"]);
    expect(matchQuery(atoms, { tag: "infra.ingesta" }).map((a) => a.id)).toEqual(["a2", "a3"]);
    expect(matchQuery(atoms, { tag: "infra" })).toHaveLength(5);
    expect(matchQuery(atoms, { tag: "inf" })).toEqual([]);
    expect(matchQuery(atoms, { text: "TOMÁS" }).map((a) => a.id)).toEqual(["a3"]);
    expect(matchQuery(atoms, { tag: "infra", kind: "hecho", status: "propuesto" }).map((a) => a.id)).toEqual(["a3"]);
    expect(matchQuery(atoms, {})).toHaveLength(6);
  });
});

describe("selectionToAtomPayload / nextAtomName", () => {
  it("arma el payload desde la selección", () => {
    const p = selectionToAtomPayload(acta.body, 0, 17, "entidad", "ActaDoc:acta");
    expect(p).toEqual({ kind: "entidad", status: "propuesto", source: "ActaDoc:acta", source_field: "body", start: 0, end: 17, tags: [], text: "Reunión del 14/09", quote: "Reunión del 14/09", conf: 1 });
  });
  it("acepta selección invertida y recorta text a 80 caracteres", () => {
    const body = "x".repeat(200);
    const p = selectionToAtomPayload(body, 150, 10, "hecho", "ActaDoc:a");
    expect(p).toMatchObject({ start: 10, end: 150 });
    expect((p.quote as string).length).toBe(140);
    expect((p.text as string).length).toBe(80);
  });
  it("nextAtomName toma el máximo aN + 1", () => {
    expect(nextAtomName([])).toBe("a1");
    expect(nextAtomName(["a1", "a10", "a3", "otro"])).toBe("a11");
  });
});

describe("validRelationTypesBetween (extremos átomo o grupo)", () => {
  const mk = (name: string, s: string[], t: string[]) => ({ id: name, name, source_types: s, target_types: t, cardinality: "", description: "" });
  const T = [
    mk("condiciona", ["AtomDoc", "GrupoDoc"], ["AtomDoc", "GrupoDoc"]),
    mk("responsable_de", ["AtomDoc", "GrupoDoc"], ["AtomDoc"]),
    mk("plazo_de", ["AtomDoc"], ["AtomDoc", "GrupoDoc"]),
    mk("solo_atomos", ["AtomDoc"], ["AtomDoc"]),
  ];
  const A = { gid: "AtomDoc:a1", model: "AtomDoc" };
  const B = { gid: "AtomDoc:a5", model: "AtomDoc" };
  const G = { gid: "GrupoDoc:riesgos", model: "GrupoDoc" };
  it("átomo -> grupo: solo tipos que admiten GrupoDoc como destino", () => {
    expect(validRelationTypesBetween(T, A, G).map((t) => t.name)).toEqual(["condiciona", "plazo_de"]);
  });
  it("grupo -> átomo: solo tipos que admiten GrupoDoc como origen", () => {
    expect(validRelationTypesBetween(T, G, B).map((t) => t.name)).toEqual(["condiciona", "responsable_de"]);
  });
  it("átomo -> átomo sigue ofreciendo todos", () => {
    expect(validRelationTypesBetween(T, A, B).map((t) => t.name)).toEqual(["condiciona", "responsable_de", "plazo_de", "solo_atomos"]);
  });
  it("grupo -> grupo y consigo mismo: nada; una arista existente se descarta", () => {
    expect(validRelationTypesBetween(T, G, { gid: "GrupoDoc:equipo", model: "GrupoDoc" })).toEqual([]);
    expect(validRelationTypesBetween(T, G, G)).toEqual([]);
    const e: Edge = { id: "x", source: "GrupoDoc:riesgos", target: "AtomDoc:a5", type: "condiciona", origin: "relation_doc", relationDoc: "r10" };
    expect(validRelationTypesBetween(T, G, B, [e]).map((t) => t.name)).toEqual(["responsable_de"]);
  });
});
