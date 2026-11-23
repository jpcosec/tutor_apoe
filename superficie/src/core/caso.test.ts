import { describe, expect, it } from "vitest";
import fixture from "./__fixtures__/atoms.json";
import { atomsFromDocuments, informesFromDocuments, kindLabel, KIND_LABELS, matchQuery } from "./atoms";
import { atomsByBase, baseOf, basesTree, groupTitle, reglasDelPrompt, respuestaProvenance, respuestasFromDocuments, sourcesFromDocuments, subgroupOf, fuentesFromDocuments } from "./caso";
import { buildPreview, parseQuery, publicationPayload, removeQueryToken, reviewGate, serializeQuery, slotField, splitRendered } from "./atom-report";
import { groupInfosFromDocuments } from "./atom-groups";
import type { Edge, GraphDocument } from "./contract";

const doc = (id: string, model_name: string, payload: Record<string, unknown>): GraphDocument => ({ id, model_name, path: `docs/${model_name === "AtomDoc" ? "atoms" : "x"}/${id}.md`, payload }) as GraphDocument;
const atomDoc = (id: string, kind: string, tags: string[], source = "FuenteDoc:folleto", extra: Record<string, unknown> = {}) =>
  doc(id, "AtomDoc", { kind, status: "propuesto", source, source_field: "body", start: 0, end: 3, tags, text: `texto ${id}`, quote: "abc", conf: 0.9, ...extra });

const DOCS: GraphDocument[] = [
  doc("system-prompt", "FuenteDoc", { title: "System prompt", tipo: "prompt", base: "Programa", descripcion: "d", body: "reglas\n\nmás" }),
  doc("mensaje-paciente", "FuenteDoc", { title: "Mensaje", tipo: "mensaje", base: "Paciente", descripcion: "", body: "hola\n\nquiero receta" }),
  doc("acta", "ActaDoc", { title: "Acta", body: "x" }),
  atomDoc("p1", "regla", ["programa.asistente"], "FuenteDoc:system-prompt"),
  atomDoc("fB", "criterio", ["programa.receta"]),
  atomDoc("f5", "logistica", ["programa.red"]),
  atomDoc("c5", "paciente", ["paciente.tratamiento"], "FuenteDoc:mensaje-paciente"),
  atomDoc("c7", "pregunta", ["paciente.intencion"], "FuenteDoc:mensaje-paciente"),
  atomDoc("c1", "paciente", ["paciente.perfil"], "FuenteDoc:mensaje-paciente"),
  doc("programa", "GrupoDoc", { title: "Programa", tag: "programa", description: "" }),
  doc("programa-asistente", "GrupoDoc", { title: "Asistente", tag: "programa.asistente", description: "x" }),
  doc("salida", "SalidaDoc", {
    title: "Salida",
    respuesta: ["docs/atoms/fB.md"],
    respuesta_titulo: "Respuesta al paciente",
    respuesta_rotulo: "Mensaje de respuesta",
    respuesta_query: "base:paciente distancia:1",
    respuesta_modo: "prosa",
    respuesta_pins: [],
    respuesta_excluidos: [],
    reglas: ["docs/atoms/p1.md"],
    reglas_titulo: "Reglas aplicadas",
    reglas_rotulo: "",
    reglas_query: "tag:asistente",
    reglas_modo: "tabla",
    reglas_pins: [],
    reglas_excluidos: [],
  }),
  doc("resp", "RespuestaDoc", {
    title: "R",
    caso: "c",
    estado: "borrador",
    generada_por: "modelo",
    slot: "respuesta",
    mensaje: "mensaje-paciente",
    respuesta: "Hola. Ok.",
    frases: [
      { texto: "Hola.", atomos: ["c5", "fB", "AtomDoc:c1"] },
      { texto: "Ok.", atomos: ["fB", "zzz"] },
    ],
  }),
];
const atoms = atomsFromDocuments(DOCS);
const edge = (id: string, source: string, target: string, type = "activa"): Edge => ({ id, source, target, type, origin: "relation", relationDoc: id });
const EDGES: Edge[] = [edge("r1", "AtomDoc:c5", "AtomDoc:fB"), edge("r2", "AtomDoc:c7", "AtomDoc:f5", "consulta_por"), edge("r3", "AtomDoc:f5", "AtomDoc:p1", "detalla")];

describe("tipos", () => {
  it("10 tipos conocidos y fallback capitalizado", () => {
    expect(Object.keys(KIND_LABELS)).toHaveLength(10);
    expect(kindLabel("paciente")).toBe("Dato del paciente");
    expect(kindLabel("logistica")).toBe("Logística");
    expect(kindLabel("nuevo_tipo")).toBe("Nuevo tipo");
    expect(kindLabel("toString")).toBe("ToString");
  });
  it("atomsFromDocuments conserva el tipo", () => {
    expect(atoms.map((a) => a.kind)).toEqual(["regla", "criterio", "logistica", "paciente", "pregunta", "paciente"]);
  });
});

describe("fuentes", () => {
  it("FuenteDoc y ActaDoc con la misma forma", () => {
    expect(fuentesFromDocuments(DOCS).map((f) => f.gid)).toEqual(["FuenteDoc:system-prompt", "FuenteDoc:mensaje-paciente"]);
    const s = sourcesFromDocuments(DOCS);
    expect(s.map((f) => f.tipo)).toEqual(["prompt", "mensaje", "acta"]);
    expect(s[0]).toMatchObject({ id: "system-prompt", base: "Programa", descripcion: "d", body: "reglas\n\nmás" });
    expect(s[2]).toMatchObject({ gid: "ActaDoc:acta", base: "", descripcion: "" });
  });
  it("sirve al store viejo", () => {
    const old = fixture.documents as unknown as GraphDocument[];
    expect(sourcesFromDocuments(old)[0]?.tipo).toBe("acta");
  });
});

describe("bases y subgrupos", () => {
  const grupos = groupInfosFromDocuments(DOCS);
  it("baseOf / subgroupOf", () => {
    expect(baseOf("paciente.situacion")).toBe("paciente");
    expect(subgroupOf("paciente.situacion")).toBe("situacion");
    expect(subgroupOf("paciente")).toBe("");
    expect(baseOf("")).toBe("");
  });
  it("groupTitle usa el GrupoDoc o capitaliza", () => {
    expect(groupTitle("programa.asistente", grupos)).toBe("Asistente");
    expect(groupTitle("asistente", grupos)).toBe("Asistente");
    expect(groupTitle("programa", grupos)).toBe("Programa");
    expect(groupTitle("paciente.situacion", grupos)).toBe("Situacion");
    expect(groupTitle("paciente", [])).toBe("Paciente");
    expect(groupTitle("x.y", [{ tag: "x.y", title: "x.y" }])).toBe("Y");
  });
  it("basesTree por primera aparición con conteos", () => {
    const t = basesTree(atoms, grupos);
    expect(t.map((b) => [b.base, b.title, b.count])).toEqual([["programa", "Programa", 3], ["paciente", "Paciente", 3]]);
    expect(t[0]!.subgroups.map((s) => [s.tag, s.title, s.count])).toEqual([["programa.asistente", "Asistente", 1], ["programa.receta", "Receta", 1], ["programa.red", "Red", 1]]);
    expect(t[1]!.subgroups[0]).toEqual({ tag: "paciente.tratamiento", title: "Tratamiento", count: 1, atomIds: ["c5"] });
  });
  it("un átomo con varios tags cuenta una vez por base", () => {
    const a = atomsFromDocuments([atomDoc("z", "regla", ["programa.a", "programa.b"])]);
    const [b] = basesTree(a);
    expect(b!.count).toBe(1);
    expect(b!.subgroups.map((s) => s.count)).toEqual([1, 1]);
  });
});

describe("informes genéricos", () => {
  const inf = informesFromDocuments(DOCS).find((i) => i.id === "salida")!;
  it("slots en el orden de las claves con título y rótulo", () => {
    expect(inf.modelName).toBe("SalidaDoc");
    expect(inf.slotList.map((s) => [s.name, s.titulo, s.rotulo, s.modo])).toEqual([["respuesta", "Respuesta al paciente", "Mensaje de respuesta", "prosa"], ["reglas", "Reglas aplicadas", "", "tabla"]]);
    expect(inf.slotList[0]!.atomos).toEqual(["docs/atoms/fB.md"]);
    expect(inf.slots.reglas).toMatchObject({ query: "tag:asistente" });
    expect(slotField("respuesta", "query")).toBe("respuesta_query");
  });
  it("el informe viejo sigue con 4 slots y títulos por defecto", () => {
    const old = informesFromDocuments(fixture.documents as unknown as GraphDocument[])[0]!;
    expect(old.slotList.map((s) => s.titulo)).toEqual(["Resumen", "Decisiones", "Riesgos", "Pendientes"]);
  });
  it("preview con títulos y tabla Criterio | Evidencia", () => {
    const withTable = { ...inf, slotList: inf.slotList.map((s) => (s.name === "respuesta" ? { ...s, modo: "tabla" as const } : s)) };
    const [s0, s1] = buildPreview(withTable.slotList, atoms, EDGES);
    expect(s0).toMatchObject({ slot: "respuesta", label: "Respuesta al paciente", rotulo: "Mensaje de respuesta", headers: ["Criterio", "Evidencia"] });
    expect(s0!.items[0]!.evidence).toBe("texto c5 (activa)");
    expect(s1!.label).toBe("Reglas aplicadas");
    expect(s1!.items[0]!.evidence).toBe("texto f5 (detalla)");
  });
  it("gate suma slots de cualquier nombre", () => {
    expect(reviewGate({ respuesta: ["a"], reglas: ["b", "c"] }).pending).toBe(3);
  });
  it("publicación parte por los títulos de los slots del informe", () => {
    const md = "---\nx: 1\n---\n\n# Salida\n\n## Respuesta al paciente\n\nHola\n\n## Reglas aplicadas\n\n- r\n";
    expect(splitRendered(md, inf.slotList).sections).toEqual({ respuesta: "Hola", reglas: "- r" });
    expect(() => splitRendered(md.replace("Reglas aplicadas", "Otra"), inf.slotList)).toThrow(/Otra/);
    const p = publicationPayload({ informe: inf, version: 1, markdown: md });
    expect(p).toMatchObject({ informe: "salida", version: 1, title: "Salida", respuesta: "Hola", reglas: "- r", atoms: ["docs/atoms/fB.md", "docs/atoms/p1.md"] });
  });
});

describe("consulta: base, distancia, tag, relacion", () => {
  const grupos = groupInfosFromDocuments(DOCS);
  it("parse y chips legibles", () => {
    const p = parseQuery("base:paciente distancia:1 tag:asistente tipo:regla relacion:activa,consulta_por libre", { grupos });
    expect(p.filters).toEqual({ kind: "regla", base: "paciente", distancia: 1, tag: "asistente", relacion: ["activa", "consulta_por"], text: "libre" });
    expect(p.tokens.map((t) => t.label)).toEqual(["Base: Paciente", "Distancia: 1 salto", "Tag: Asistente", "Tipo: Regla", "Relación: activa, consulta por", "libre"]);
    expect(parseQuery("distancia:3").tokens[0]!.label).toBe("Distancia: 3 saltos");
  });
  it("valores inválidos quedan inactivos", () => {
    const p = parseQuery("distancia:x distancia:-1 distancia:2 distancia:3 base:a base:b tipo:zzz");
    expect(p.tokens.map((t) => t.active)).toEqual([false, false, true, false, true, true, false]);
    expect(p.filters).toEqual({ distancia: 2, base: ["a", "b"] });
    expect(parseQuery("tipo:zzz", { kinds: ["zzz"] }).filters.kind).toBe("zzz");
  });
  it("ida y vuelta y quitar chip", () => {
    const q = "base:paciente distancia:1 tag:asistente";
    expect(serializeQuery(parseQuery(q).tokens)).toBe(q);
    expect(removeQueryToken(q, 1)).toBe("base:paciente tag:asistente");
  });
  it("base y tag (segmento suelto) filtran", () => {
    const ids = (q: string) => matchQuery(atoms, parseQuery(q).filters, EDGES).map((a) => a.id);
    expect(ids("base:paciente")).toEqual(["c5", "c7", "c1"]);
    expect(ids("BASE:Programa")).toEqual(["p1", "fB", "f5"]);
    expect(ids("tag:asistente")).toEqual(["p1"]);
    expect(ids("tag:programa.receta")).toEqual(["fB"]);
    expect(ids("tipo:paciente base:paciente")).toEqual(["c5", "c1"]);
    expect(ids("relacion:activa")).toEqual(["fB", "c5"]);
    // base y tag son pertenencia a grupo y se unen con O
    expect(ids("base:paciente tag:asistente")).toEqual(["p1", "c5", "c7", "c1"]);
    expect(ids("base:paciente tag:asistente tipo:paciente")).toEqual(["c5", "c1"]);
    expect(ids("base:paciente base:programa")).toHaveLength(6);
    // el texto libre solo filtra sin otros filtros
    expect(ids("tag:asistente reglas del asistente que condicionan")).toEqual(["p1"]);
    expect(ids("zzz")).toEqual([]);
    expect(ids("receta")).toEqual(["fB"]);
    expect(ids("texto fB")).toEqual(["fB"]);
  });
  it("distancia:N amplía las semillas con vecinos a N saltos (no dirigido)", () => {
    const ids = (q: string) => matchQuery(atoms, parseQuery(q).filters, EDGES).map((a) => a.id);
    expect(ids("base:paciente distancia:0")).toEqual(["c5", "c7", "c1"]);
    expect(ids("base:paciente distancia:1")).toEqual(["fB", "f5", "c5", "c7", "c1"].sort((a, b) => atoms.findIndex((x) => x.id === a) - atoms.findIndex((x) => x.id === b)));
    expect(ids("base:paciente distancia:2")).toContain("p1");
    expect(ids("tag:asistente distancia:1")).toEqual(["p1", "f5"]);
    expect(ids("distancia:1")).toEqual([]);
    expect(matchQuery(atoms, { base: "paciente", distancia: 1 }).map((a) => a.id)).toEqual(["c5", "c7", "c1"]);
  });
  it("las relaciones sobre un grupo llegan a sus átomos", () => {
    const g: Edge = edge("rg", "GrupoDoc:programa-red", "AtomDoc:c1", "restringe");
    const r = matchQuery(atoms, { tipo: undefined, kind: "paciente", tag: "perfil", distancia: 1 } as never, [g]).map((a) => a.id);
    expect(r).toEqual(["f5", "c1"]);
  });
});

describe("respuesta", () => {
  const [r] = respuestasFromDocuments(DOCS);
  it("lectura y tolerancia", () => {
    expect(r).toMatchObject({ id: "resp", generadaPor: "modelo", slot: "respuesta", mensaje: "mensaje-paciente", estado: "borrador" });
    expect(r!.frases).toHaveLength(2);
    const [e] = respuestasFromDocuments([doc("x", "RespuestaDoc", { frases: [5, "solo texto", { atomos: "no" }] })]);
    expect(e).toMatchObject({ id: "x", title: "x", caso: "", respuesta: "solo texto " });
    expect(e!.frases).toEqual([{ texto: "solo texto", atomos: [] }, { texto: "", atomos: [] }]);
  });
  it("procedencia por frase, 1-based, resolviendo id/gid/ruta", () => {
    const prov = respuestaProvenance(r!, atoms);
    expect(prov.map((p) => [p.n, p.atomos.map((a) => a.id), p.missing])).toEqual([[1, ["c5", "fB", "c1"], []], [2, ["fB"], ["zzz"]]]);
  });
  it("átomos por base con sus frases", () => {
    const g = atomsByBase(r!, atoms, ["p1", "fB", "f5", "c5", "c7"], groupInfosFromDocuments(DOCS));
    expect(g.map((b) => [b.base, b.title, b.atoms.map((u) => [u.atom.id, u.frases])])).toEqual([
      ["programa", "Programa", [["p1", []], ["fB", [1, 2]], ["f5", []]]],
      ["paciente", "Paciente", [["c5", [1]], ["c7", []], ["c1", [1]]]],
    ]);
    expect(atomsByBase(r!, atoms).map((b) => b.base)).toEqual(["paciente", "programa"]);
  });
  it("reglas del system prompt", () => {
    const rules = reglasDelPrompt(r!, atoms, sourcesFromDocuments(DOCS));
    expect(rules.map((u) => u.atom.id)).toEqual(["p1"]);
    expect(rules[0]!.frases).toEqual([]);
  });
});
