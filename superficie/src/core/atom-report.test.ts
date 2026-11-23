import { describe, expect, it } from "vitest";
import fixture from "./__fixtures__/atoms.json";
import { atomsFromDocuments, informesFromDocuments, matchQuery } from "./atoms";
import { buildPreview, latestVersion, NO_RELATION, nextVersion, publicationName, publicationPayload, publicationsOf, publishState, snapshotAtoms, splitRendered, parseQuery, removeQueryToken, reviewGate, serializeQuery, slotChanges, slotField } from "./atom-report";
import type { Edge, GraphDocument, InformeSlot } from "./contract";

const docs = fixture.documents as unknown as GraphDocument[];
const atoms = atomsFromDocuments(docs);
const edges = fixture.edges as Edge[];
const informe = informesFromDocuments(docs).find((i) => i.id === "inf1")!;

describe("parseQuery", () => {
  it("convierte filtros y texto libre a AtomFilters", () => {
    const p = parseQuery("tipo:decision tag:infra.ingesta estado:confirmado cola eventos");
    expect(p.filters).toEqual({ kind: "decision", tag: "infra.ingesta", status: "confirmado", text: "cola eventos" });
    expect(p.tokens.map((t) => t.kind)).toEqual(["tipo", "tag", "estado", "texto", "texto"]);
  });
  it("ida y vuelta: serialize(parse(q)) normaliza espacios y conserva tokens", () => {
    const q = "tipo:riesgo  tag:infra   volumen tipo:hecho";
    expect(serializeQuery(parseQuery(q).tokens)).toBe("tipo:riesgo tag:infra volumen tipo:hecho");
    expect(parseQuery(q).filters.kind).toEqual(["riesgo", "hecho"]);
  });
  it("valores inválidos no filtran pero se conservan como chip inactivo", () => {
    const p = parseQuery("tipo:foo estado:nada tag:a tag:b");
    expect(p.filters).toEqual({ tag: ["a", "b"] });
    expect(p.tokens.map((t) => t.active)).toEqual([false, false, true, true]);
  });
  it("consulta vacía y prefijo desconocido como texto", () => {
    expect(parseQuery("").filters).toEqual({});
    expect(parseQuery("otro:x").filters).toEqual({ text: "otro:x" });
  });
  it("removeQueryToken reescribe sin el chip", () => {
    expect(removeQueryToken("tipo:decision tag:infra cola", 1)).toBe("tipo:decision cola");
    expect(removeQueryToken("solo", 0)).toBe("");
  });
  it("los filtros funcionan con matchQuery", () => {
    const r = matchQuery(atoms, parseQuery("tipo:decision").filters);
    expect(r.map((a) => a.id)).toEqual(["a2"]);
  });
});

describe("slotChanges / slotField", () => {
  const base: InformeSlot = { atomos: ["p1"], query: "", pins: [], excluidos: [], modo: "viñetas" };
  it("una entrada por campo cambiado", () => {
    expect(slotChanges("riesgos", base, { ...base, atomos: ["p1", "p2"] })).toEqual([{ field: "riesgos", value: ["p1", "p2"] }]);
    expect(slotChanges("riesgos", base, { ...base, atomos: [], excluidos: ["p1"] })).toEqual([
      { field: "riesgos", value: [] },
      { field: "riesgos_excluidos", value: ["p1"] },
    ]);
    expect(slotChanges("riesgos", base, base)).toEqual([]);
  });
  it("nombres de campo", () => {
    expect(slotField("resumen", "atomos")).toBe("resumen");
    expect(slotField("resumen", "pins")).toBe("resumen_pins");
    expect(slotField("resumen", "modo")).toBe("resumen_modo");
    expect(slotField("resumen", "query")).toBe("resumen_query");
  });
});

describe("reviewGate", () => {
  it("suma nuevos de todos los slots", () => {
    expect(reviewGate({ resumen: ["a"], riesgos: ["b", "c"] })).toEqual({ pending: 3, ready: false, label: "3 átomos nuevos por revisar" });
    expect(reviewGate({ resumen: ["a"] }).label).toBe("1 átomo nuevo por revisar");
  });
  it("sin nuevos está listo", () => {
    expect(reviewGate({})).toEqual({ pending: 0, ready: true, label: "Listo para publicar" });
    expect(reviewGate({ resumen: [] }).ready).toBe(true);
  });
});

describe("buildPreview", () => {
  const sections = buildPreview(informe.slots, atoms, edges);
  const by = (s: string) => sections.find((x) => x.slot === s)!;
  it("siempre los 4 slots en orden", () => {
    expect(sections.map((s) => s.slot)).toEqual(["resumen", "decisiones", "riesgos", "pendientes"]);
  });
  it("prosa une los textos y conserva procedencia por frase", () => {
    const s = by("resumen");
    expect(s.modo).toBe("prosa");
    expect(s.prose).toBe("Reunión del 14/09.");
    expect(s.items[0]!.atoms.map((a) => a.id)).toEqual(["a1"]);
  });
  it("viñetas: un ítem por átomo y sin prosa", () => {
    const s = by("decisiones");
    expect(s.items.map((i) => i.text)).toEqual(["Reemplazar el lote por una cola"]);
    expect(s.prose).toBe("");
  });
  it("tabla: relación desde edges o Sin relación", () => {
    const slots = { ...informe.slots, pendientes: { ...informe.slots.pendientes, modo: "tabla" as const, atomos: ["docs/atoms/a5.md", "docs/atoms/a2.md", "docs/atoms/a1.md"] } };
    const s = buildPreview(slots, atoms, edges).find((x) => x.slot === "pendientes")!;
    expect(s.items[0]!.relation).toContain("motiva → Reemplazar el lote por una cola");
    expect(s.items[1]!.relation).toContain("motiva este");
    expect(s.items[2]!.relation).toBe(NO_RELATION);
  });
  it("slot sin átomos queda vacío; rutas desconocidas van a missing", () => {
    expect(by("pendientes").empty).toBe(true);
    const slots = { ...informe.slots, resumen: { ...informe.slots.resumen, atomos: ["docs/atoms/zzz.md"] } };
    const s = buildPreview(slots, atoms, edges)[0]!;
    expect(s.empty).toBe(true);
    expect(s.missing).toEqual(["docs/atoms/zzz.md"]);
  });
});

describe("publicación", () => {
  const pub = (id: string, version: unknown, informe = "inf1"): GraphDocument => ({ id, model_name: "PublicacionDoc", path: `docs/${id}.md`, payload: { informe, version, title: "T", atoms: ["docs/atoms/a1.md"] } });
  const RENDER = "---\nresumen_modo: prosa\n---\n\n# Titulo\n\n## Resumen\n\n- uno\n- dos\n\n## Decisiones\n\n## Riesgos\n\ntexto\n\n## Pendientes\n\n- p\n";

  it("versiones: filtra por informe, ordena, siguiente y nombre", () => {
    const list = publicationsOf([pub("inf1-v2", 2), pub("inf1-v1", 1), pub("otro-v7", 7, "otro"), pub("mala", "x")], "inf1");
    expect(list.map((p) => p.version)).toEqual([1, 2]);
    expect(latestVersion(list)).toBe(2);
    expect(nextVersion(list)).toBe(3);
    expect(nextVersion([])).toBe(1);
    expect(publicationName("inf1", 3)).toBe("inf1-v3");
  });

  it("splitRendered quita el frontmatter y parte por slot", () => {
    const { title, sections } = splitRendered(RENDER);
    expect(title).toBe("Titulo");
    expect(sections).toEqual({ resumen: "- uno\n- dos", decisiones: "", riesgos: "texto", pendientes: "- p" });
  });

  it("splitRendered no descarta secciones desconocidas", () => {
    expect(() => splitRendered("# T\n\n## Otra\n\nx")).toThrow(/Otra/);
  });

  it("payload de la foto: átomos únicos de todos los slots y secciones del render", () => {
    const payload = publicationPayload({ informe, version: 4, markdown: RENDER });
    expect(payload).toMatchObject({ informe: "inf1", version: 4, title: "Titulo", resumen: "- uno\n- dos", pendientes: "- p" });
    expect(payload.atoms).toEqual(snapshotAtoms(informe.slots));
    expect(new Set(payload.atoms as string[]).size).toBe((payload.atoms as string[]).length);
  });

  it("estado del botón", () => {
    const ok = reviewGate({});
    expect(publishState({ gate: ok, publications: [{ version: 2 }], atomCount: 3, publishing: false })).toEqual({ label: "Publicar v3", enabled: true, reason: "", published: "Publicado como v2" });
    expect(publishState({ gate: ok, publications: [], atomCount: 3, publishing: false })).toMatchObject({ label: "Publicar v1", enabled: true, published: "Sin publicar" });
    expect(publishState({ gate: reviewGate({ resumen: ["x"] }), publications: [{ version: 2 }], atomCount: 3, publishing: false })).toMatchObject({ enabled: false, reason: "Revisa los átomos nuevos antes de republicar" });
    expect(publishState({ gate: ok, publications: [], atomCount: 0, publishing: false }).enabled).toBe(false);
    expect(publishState({ gate: ok, publications: [], atomCount: 2, publishing: true })).toMatchObject({ enabled: false, reason: "Publicando…" });
  });
});
