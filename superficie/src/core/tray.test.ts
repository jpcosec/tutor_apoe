import { describe, expect, it } from "vitest";
import type { GraphDocument, SchemaField, SchemaIndexLike } from "./contract";
import type { RankHit } from "./contract";
import { collectTray, groupByModel, indexIdOf, isDraftTagged, lacksProvenance, pickSuggestions, placedIds, trayQuery } from "./tray";

const doc = (id: string, model: string, payload: Record<string, unknown>): GraphDocument =>
  ({ id, model_name: model, path: `${model}/${id}.md`, version: "v", payload }) as GraphDocument;

/** Schema que declara `provenance` solo para los modelos nombrados. */
const schemaFor = (models: string[]): SchemaIndexLike => ({
  field: (model, path) => (path === "provenance" && models.includes(model) ? ({ name: "provenance" } as SchemaField) : undefined),
});

describe("lacksProvenance", () => {
  const declares = (model: string, field: string) => field === "provenance" && model === "DomainAtom";

  it("es borrador si el modelo declara procedencia y está vacía", () => {
    expect(lacksProvenance(doc("d1", "DomainAtom", { provenance: "" }), declares)).toBe(true);
    expect(lacksProvenance(doc("d2", "DomainAtom", {}), declares)).toBe(true);
  });

  it("no es borrador si tiene procedencia", () => {
    expect(lacksProvenance(doc("d3", "DomainAtom", { provenance: "source/x.md" }), declares)).toBe(false);
  });

  it("un modelo que NO declara procedencia nunca entra: la regla no le aplica", () => {
    expect(lacksProvenance(doc("r1", "RelationDoc", {}), declares)).toBe(false);
  });
});

describe("isDraftTagged", () => {
  it("reconoce status:draft sin importar mayúsculas", () => {
    expect(isDraftTagged(doc("d", "M", { tags: ["Status:Draft"] }))).toBe(true);
  });

  it("ignora tags que no marcan borrador", () => {
    expect(isDraftTagged(doc("d", "M", { tags: ["domain:cobranza"] }))).toBe(false);
  });

  it("tolera un payload sin tags o con tags que no son lista", () => {
    expect(isDraftTagged(doc("d", "M", {}))).toBe(false);
    expect(isDraftTagged(doc("d", "M", { tags: "draft" }))).toBe(false);
  });
});

describe("collectTray", () => {
  const docs = [
    doc("con-origen", "DomainAtom", { provenance: "source/a.md", title: "Con origen" }),
    doc("sin-origen", "DomainAtom", { provenance: "", title: "Sin origen", summary: "resumen" }),
    doc("relacion", "RelationDoc", {}),
    doc("borrador", "RuleAtom", { tags: ["status:draft"] }),
  ];

  it("solo trae lo que cae en la bandeja, con su motivo", () => {
    const tray = collectTray(docs, schemaFor(["DomainAtom"]));
    expect(tray.map((entry) => entry.doc)).toEqual(["sin-origen", "borrador"]);
    expect(tray[0]?.reasons).toEqual(["sin-procedencia"]);
    expect(tray[1]?.reasons).toEqual(["marcado-borrador"]);
  });

  it("sin schema no se inventa la regla de procedencia", () => {
    const tray = collectTray(docs, null);
    expect(tray.map((entry) => entry.doc)).toEqual(["borrador"]);
  });

  it("usa el título del payload y cae al id cuando falta", () => {
    const tray = collectTray(docs, schemaFor(["DomainAtom"]));
    expect(tray[0]?.title).toBe("Sin origen");
    expect(tray[1]?.title).toBe("borrador");
  });
});

describe("groupByModel", () => {
  it("ordena los grupos por cantidad y desempata por nombre", () => {
    const entries = collectTray(
      [
        doc("a", "DomainAtom", { provenance: "" }),
        doc("b", "DomainAtom", { provenance: "" }),
        doc("c", "RuleAtom", { provenance: "" }),
      ],
      schemaFor(["DomainAtom", "RuleAtom"]),
    );
    expect(groupByModel(entries).map((group) => [group.model, group.entries.length])).toEqual([
      ["DomainAtom", 2],
      ["RuleAtom", 1],
    ]);
  });
});

describe("sugerencias de destino (lógica pura)", () => {
  it("trayQuery junta título y strings del payload, aplana espacios y acota", () => {
    const d = doc("d1", "M", { title: "Hola", body: "uno\n\n  dos", tags: ["a", 3, "b"], n: 5, nested: { x: "no" } });
    expect(trayQuery(d)).toBe("Hola Hola uno dos a b");
    expect(trayQuery(doc("d2", "M", { body: "x".repeat(1000) })).length).toBe(400);
  });

  it("placedIds excluye lo que está en la bandeja y nombra como Model:name", () => {
    const docs = [doc("a", "AtomDoc", {}), doc("b", "AtomDoc", {}), doc("c", "ActaDoc", {})];
    const entries = collectTray(docs, null).concat([{ doc: "b" } as never]);
    expect(placedIds(docs, entries)).toEqual(["AtomDoc:a", "ActaDoc:c"]);
    expect(indexIdOf(docs[2]!)).toBe("ActaDoc:c");
  });

  const hit = (name: string, score: number, title?: string): RankHit =>
    ({ id: `M:${name}`, model: "M", name, score, payload: title ? { title } : {}, tags: [] }) as RankHit;

  it("pickSuggestions ordena, aplica umbral y tope de 3, y no se sugiere a sí mismo", () => {
    const hits = [hit("low", 0.1), hit("b", 0.5), hit("self", 0.99), hit("a", 0.62, "Título A"), hit("c", 0.4), hit("d", 0.36)];
    const out = pickSuggestions(hits, "self");
    expect(out.map((s) => s.name)).toEqual(["a", "b", "c"]);
    expect(out[0]).toMatchObject({ title: "Título A", percent: 62, score: 0.62 });
    expect(out[1]!.title).toBe("b");
  });

  it("sin hits que alcancen el umbral no hay sugerencias", () => {
    expect(pickSuggestions([hit("x", 0.2)], "s")).toEqual([]);
  });
});
