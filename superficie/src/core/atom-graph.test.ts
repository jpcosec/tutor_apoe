import { describe, expect, it } from "vitest";
import fixture from "./__fixtures__/atoms.json";
import { atomsFromDocuments, relationTypesFromDocuments } from "./atoms";
import {
  NO_GROUP,
  assignLanes,
  atomLinks,
  boxesOverlap,
  clipToBox,
  edgeGeometry,
  filterEdges,
  fitView,
  fuseLinks,
  highlightAtoms,
  highlightKeys,
  hitTest,
  layoutRegions,
  nextRelationName,
  nodeAt,
  nodeKeyOf,
  primaryGroup,
  relationPayload,
  relationPayloadBetween,
  relationTypeNames,
  screenToWorld,
  wrapLines,
  zoomAt,
} from "./atom-graph";
import type { Atom, Edge, GraphDocument } from "./contract";

const docs = fixture.documents as unknown as GraphDocument[];
const edges = fixture.edges as Edge[];
const all = atomsFromDocuments(docs);
const visible = all.filter((a) => a.status !== "descartado");
const types = relationTypesFromDocuments(docs);

function fake(n: number, tagOf: (i: number) => string[]): Atom[] {
  return Array.from({ length: n }, (_, i) => ({ ...all[0]!, id: `x${i}`, gid: `AtomDoc:x${i}`, path: `docs/atoms/x${i}.md`, tags: tagOf(i) }));
}

describe("grupos", () => {
  it("el grupo principal es el primer segmento del primer tag", () => {
    expect(primaryGroup({ tags: ["infra.ingesta", "arquitectura"] })).toBe("infra");
    expect(primaryGroup({ tags: [] })).toBe(NO_GROUP);
  });
  it("resalta por prefijo de grupo", () => {
    expect([...highlightAtoms(visible, "infra")].sort()).toEqual(["AtomDoc:a2", "AtomDoc:a3", "AtomDoc:a4", "AtomDoc:a5"]);
    expect([...highlightAtoms(visible, "infra.ingesta")].sort()).toEqual(["AtomDoc:a2", "AtomDoc:a3"]);
    expect([...highlightAtoms(visible, "arquitectura")]).toEqual(["AtomDoc:a2"]);
    expect(highlightAtoms(visible, null).size).toBe(0);
  });
  it("un grupo plegado resalta su nodo-grupo", () => {
    expect([...highlightKeys(visible, "infra.ingesta", new Set(["infra"]))]).toEqual(["group:infra"]);
  });
});

describe("layoutRegions", () => {
  it("es determinista y no solapa nodos ni regiones (N arbitrario)", () => {
    for (const n of [1, 2, 7, 23, 60]) {
      const list = fake(n, (i) => (i % 5 === 0 ? [] : [`g${i % 4}.sub`]));
      const a = layoutRegions(list);
      const b = layoutRegions(list);
      expect(a).toEqual(b);
      expect(a.nodes).toHaveLength(n);
      for (let i = 0; i < a.regions.length; i++)
        for (let j = i + 1; j < a.regions.length; j++) expect(boxesOverlap(a.regions[i]!, a.regions[j]!)).toBe(false);
      for (let i = 0; i < a.nodes.length; i++)
        for (let j = i + 1; j < a.nodes.length; j++) expect(boxesOverlap(a.nodes[i]!, a.nodes[j]!)).toBe(false);
      // cada nodo queda dentro de su región
      for (const r of a.regions)
        for (const k of r.nodeKeys) {
          const nd = a.byKey[k]!;
          expect(nd.x).toBeGreaterThanOrEqual(r.x);
          expect(nd.y).toBeGreaterThanOrEqual(r.y);
          expect(nd.x + nd.w).toBeLessThanOrEqual(r.x + r.w);
          expect(nd.y + nd.h).toBeLessThanOrEqual(r.y + r.h);
        }
    }
  });
  it("agrupa por grupo principal, sin grupo al final; un átomo multi-tag aparece una vez", () => {
    const l = layoutRegions(visible);
    expect(l.regions.map((r) => r.group)).toEqual(["infra", "reuniones"]);
    expect(l.nodes.filter((n) => n.atomId === "a2")).toHaveLength(1);
  });
  it("las regiones saltan de fila al pasar maxWidth", () => {
    const l = layoutRegions(fake(12, (i) => [`g${i}`]), new Set(), { maxWidth: 400 });
    expect(new Set(l.regions.map((r) => r.y)).size).toBeGreaterThan(1);
    expect(l.height).toBeGreaterThan(0);
  });
  it("plegar reemplaza los átomos por un solo nodo-grupo", () => {
    const l = layoutRegions(visible, new Set(["infra"]));
    const region = l.regions.find((r) => r.group === "infra")!;
    expect(region.collapsed).toBe(true);
    expect(region.nodeKeys).toEqual(["group:infra"]);
    expect(l.byKey["group:infra"]).toMatchObject({ kind: "group", count: 4 });
    expect(l.byKey["AtomDoc:a2"]).toBeUndefined();
  });
  it("sin átomos, layout vacío", () => {
    expect(layoutRegions([])).toMatchObject({ regions: [], nodes: [], width: 0, height: 0 });
  });
});

describe("aristas", () => {
  it("directas entre átomos; la de acta se ignora; la de grupo se hereda punteada", () => {
    const links = atomLinks(edges, visible);
    const direct = links.filter((l) => !l.inherited);
    expect(direct.map((l) => `${l.source}>${l.target}`)).toEqual(["AtomDoc:a5>AtomDoc:a2"]);
    const inh = links.filter((l) => l.inherited);
    // semantic_tag/infra → a2 se proyecta sobre miembros de infra distintos de a2
    expect(inh.map((l) => l.source).sort()).toEqual(["AtomDoc:a3", "AtomDoc:a4"]);
    expect(inh.every((l) => l.target === "AtomDoc:a2" && l.via === "infra" && l.kind === "relation")).toBe(true);
  });
  it("un GrupoDoc como extremo ya no se ignora: se hereda punteado hacia/desde cada átomo del grupo", () => {
    const g: Edge = { id: "r10", source: "GrupoDoc:infra-ingesta", target: "AtomDoc:a1", type: "condiciona", origin: "relation_doc", relationDoc: "r10" };
    const inh = atomLinks([g], visible).filter((l) => l.inherited);
    expect(inh.length).toBeGreaterThan(0);
    expect(inh.every((l) => l.edge.id === "r10" && l.target === "AtomDoc:a1" && l.via === "infra.ingesta" && l.kind === "relation")).toBe(true);
    const back: Edge = { id: "r11", source: "AtomDoc:a1", target: "GrupoDoc:infra", type: "afecta", origin: "relation_doc", relationDoc: "r11" };
    const out = atomLinks([back], visible).filter((l) => l.inherited);
    expect(out.every((l) => l.source === "AtomDoc:a1")).toBe(true);
    // los miembros de un subgrupo también heredan la relación puesta sobre el padre
    expect(new Set(out.map((l) => l.target))).toEqual(new Set(visible.filter((a) => a.tags.some((t) => t === "infra" || t.startsWith("infra."))).map((a) => a.gid).filter((x) => x !== "AtomDoc:a1")));
  });
  it("relationPayloadBetween arma el RelationDoc con un GrupoDoc de extremo", () => {
    const p = relationPayloadBetween({ gid: "GrupoDoc:riesgos", label: "Grupo riesgos" }, { gid: "AtomDoc:a5", label: "Migración" }, { id: "c", name: "condiciona", source_types: [], target_types: [], cardinality: "", description: "" });
    expect(p).toMatchObject({ source_id: "GrupoDoc:riesgos", target_id: "AtomDoc:a5", relation_type: "condiciona", title: "Grupo riesgos condiciona Migración" });
  });
  it("origin reference es tenue (kind reference)", () => {
    const e: Edge = { id: "z", source: "AtomDoc:a1", target: "AtomDoc:a2", type: "menciona", origin: "reference", relationDoc: null };
    const [l] = atomLinks([e], visible);
    expect(l!.kind).toBe("reference");
  });
  it("plegar fusiona aristas de los átomos del grupo y descarta las internas", () => {
    const links = atomLinks(edges, visible);
    const open = fuseLinks(links, visible, new Set());
    expect(open).toHaveLength(3);
    const folded = fuseLinks(links, visible, new Set(["infra"]));
    // a2..a5 son todos de infra: todas las aristas son internas y desaparecen
    expect(folded).toEqual([]);
    // con reuniones plegado y a1 conectado a un átomo de infra, queda una arista entre nodos-grupo
    const extra = atomLinks([...edges, { id: "n", source: "AtomDoc:a1", target: "AtomDoc:a3", type: "motiva", origin: "relation", relationDoc: "r9" }], visible);
    const two = fuseLinks(extra, visible, new Set(["infra", "reuniones"]));
    expect(two).toHaveLength(1);
    expect(two[0]).toMatchObject({ source: "group:reuniones", target: "group:infra", count: 1 });
  });
  it("fusiona duplicados y cuenta", () => {
    const list = fake(4, (i) => (i < 2 ? ["g"] : ["h"]));
    const es: Edge[] = [
      { id: "1", source: "AtomDoc:x0", target: "AtomDoc:x2", type: "t", origin: "relation", relationDoc: "r1" },
      { id: "2", source: "AtomDoc:x1", target: "AtomDoc:x3", type: "t", origin: "relation", relationDoc: "r2" },
      { id: "3", source: "AtomDoc:x1", target: "AtomDoc:x3", type: "u", origin: "relation", relationDoc: "r3" },
    ];
    const fused = fuseLinks(atomLinks(es, list), list, new Set(["g", "h"]));
    expect(fused).toHaveLength(2);
    const t = fused.find((e) => e.type === "t")!;
    expect(t).toMatchObject({ source: "group:g", target: "group:h", count: 2, edgeIds: ["1", "2"], relationDocs: ["r1", "r2"] });
    expect(nodeKeyOf(list[0]!, new Set(["g"]))).toBe("group:g");
  });
  it("filtra por tipo y por referencias", () => {
    const fused = fuseLinks(
      atomLinks(
        [
          { id: "1", source: "AtomDoc:a5", target: "AtomDoc:a2", type: "motiva", origin: "relation", relationDoc: "r1" },
          { id: "2", source: "AtomDoc:a1", target: "AtomDoc:a2", type: "ref", origin: "reference", relationDoc: null },
        ],
        visible,
      ),
      visible,
      new Set(),
    );
    expect(filterEdges(fused, new Set(["motiva"]), true).map((e) => e.type)).toEqual(["ref"]);
    expect(filterEdges(fused, new Set(), false).map((e) => e.type)).toEqual(["motiva"]);
  });
  it("tipos: declarados de átomo + los de relaciones existentes (sin los estructurales)", () => {
    const structural = { ...types[0]!, name: "has_model", source_types: ["sldb_store"], target_types: ["sldb_model"] };
    expect(relationTypeNames([...types, structural], [{ id: "q", source: "", target: "", type: "nuevo", origin: "relation", relationDoc: "r" }])).toEqual(["motiva", "nuevo"]);
  });
});

describe("geometría", () => {
  const A = { x: 0, y: 0, w: 100, h: 50 };
  const B = { x: 300, y: 0, w: 100, h: 50 };
  it("recorta la línea al borde de la caja", () => {
    expect(clipToBox(A, { x: 300, y: 25 })).toEqual({ x: 100, y: 25 });
  });
  it("carriles centrados para aristas paralelas, sin importar el sentido", () => {
    const lanes = assignLanes([
      { key: "1", source: "a", target: "b" },
      { key: "2", source: "b", target: "a" },
      { key: "3", source: "a", target: "c" },
    ]);
    expect(lanes).toEqual({ "1": -0.5, "2": 0.5, "3": 0 });
  });
  it("a→b y b→a con carriles distintos no coinciden", () => {
    const g1 = edgeGeometry(A, B, -0.5, "a", "b");
    const g2 = edgeGeometry(B, A, 0.5, "b", "a");
    expect(g1.mid.y).not.toBeCloseTo(g2.mid.y);
    expect(edgeGeometry(A, B, 0, "a", "b").mid).toEqual({ x: 200, y: 25 });
  });
  it("hit-testing: nodo bajo el punto", () => {
    const l = layoutRegions(visible);
    const n = l.nodes[1]!;
    expect(nodeAt(l, { x: n.x + 3, y: n.y + 3 })).toBe(n.key);
    expect(nodeAt(l, { x: -50, y: -50 })).toBeNull();
    expect(hitTest([A, B], { x: 350, y: 10 })).toBe(1);
  });
  it("zoom mantiene fijo el punto bajo el cursor; ajustar encuadra", () => {
    const v = zoomAt({ x: 10, y: 20, k: 1 }, 2, { x: 110, y: 120 });
    expect(screenToWorld(v, { x: 110, y: 120 })).toEqual({ x: 100, y: 100 });
    const f = fitView({ width: 2000, height: 500 }, { width: 1000, height: 800 });
    expect(f.k).toBeCloseTo(0.476, 2);
    expect(fitView({ width: 100, height: 100 }, { width: 1000, height: 800 }).k).toBe(1);
    expect(fitView({ width: 100, height: 100 }, { width: 0, height: 0 })).toEqual({ x: 0, y: 0, k: 1 });
  });
});

describe("crear relación", () => {
  it("nombre rel-<n> libre a partir de los RelationDoc", () => {
    expect(nextRelationName(docs)).toBe("rel-1");
    expect(
      nextRelationName([
        { id: "rel-3", model_name: "RelationDoc" },
        { id: "rel-9x", model_name: "RelationDoc" },
        { id: "rel-20", model_name: "AtomDoc" },
        { id: "r1", model_name: "RelationDoc" },
      ]),
    ).toBe("rel-4");
  });
  it("payload con gids, tipo y campos vacíos", () => {
    const a = all.find((x) => x.id === "a5")!;
    const b = all.find((x) => x.id === "a2")!;
    expect(relationPayload(a, b, types.find((t) => t.name === "motiva")!)).toMatchObject({
      source_id: "AtomDoc:a5",
      target_id: "AtomDoc:a2",
      relation_type: "motiva",
      condition: "",
      notes: "",
    });
  });
});

describe("wrapLines", () => {
  it("parte por palabras y recorta la última línea", () => {
    expect(wrapLines("Reemplazar el lote por una cola", 14, 2)).toEqual(["Reemplazar el", "lote por una …"]);
    expect(wrapLines("corto", 14, 2)).toEqual(["corto"]);
    expect(wrapLines("", 14, 2)).toEqual([]);
    expect(wrapLines("supercalifragilisticoespialidoso", 10, 2)).toEqual(["supercali…"]);
  });
});
