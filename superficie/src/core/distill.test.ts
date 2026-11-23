import { describe, expect, it } from "vitest";
import type { GraphDocument } from "./contract";
import type { FieldRankHit } from "./contract";
import {
  AMONG_MAX_CHARS,
  amongIds,
  classifyMatches,
  collectAnchors,
  distill,
  parseRef,
  rankRequest,
  SIMILAR_K,
  SIMILAR_K_UNSCOPED,
  similarityQuery,
  suggestTemplate,
  type AnchorEntry,
} from "./distill";

const anchor = (doc: string, symbol: string, ref: string, motive: string): AnchorEntry => ({ doc, symbol, ref, motive });

describe("parseRef · s-expression", () => {
  it("lee el tipo del primer átomo", () => {
    expect(parseRef("(model DomainAtom)")).toMatchObject({ kind: "model", model: "DomainAtom" });
    expect(parseRef("(field ConversationStep instructions)")).toMatchObject({
      kind: "field",
      model: "ConversationStep",
      field: "instructions",
    });
    expect(parseRef("(relation grounded_by)")).toMatchObject({ kind: "relation", relation: "grounded_by" });
  });

  it("el predicado va completo, con espacios, y no es un campo", () => {
    expect(parseRef('(where DomainAtom "se paga con transferencia")')).toMatchObject({
      kind: "where",
      model: "DomainAtom",
      predicate: "se paga con transferencia",
    });
  });

  it("el doc toma el modelo de la parte izquierda del nombre", () => {
    expect(parseRef('(doc "DomainAtom:domain-ubicacion")')).toMatchObject({ kind: "doc", model: "DomainAtom" });
  });

  it("desarma change y move", () => {
    expect(parseRef('(change (it "it" DomainAtom) answer "v")')).toMatchObject({
      kind: "change",
      model: "DomainAtom",
      field: "answer",
    });
    expect(parseRef("(move (create RuleAtom) (assert x y))")).toMatchObject({ kind: "move", model: "RuleAtom" });
  });

  it("un primer átomo desconocido cae en other", () => {
    expect(parseRef("(compose a b)")).toMatchObject({ kind: "other" });
  });
});

describe("parseRef · refs viejos en string", () => {
  it("lee las formas heredadas", () => {
    expect(parseRef("model:DomainAtom")).toMatchObject({ kind: "model", model: "DomainAtom" });
    expect(parseRef("predicate:DomainAtom:se paga")).toMatchObject({ kind: "where", model: "DomainAtom", predicate: "se paga" });
    expect(parseRef("action:change DomainAtom.answer=v")).toMatchObject({
      kind: "change",
      model: "DomainAtom",
      field: "answer",
    });
    expect(parseRef("field:DomainAtom.answer")).toMatchObject({ kind: "field", model: "DomainAtom", field: "answer" });
    expect(parseRef("relation:grounded_by")).toMatchObject({ kind: "relation", relation: "grounded_by" });
  });

  it("no reconoce compose ni un ref vacío", () => {
    expect(parseRef("compose")).toMatchObject({ kind: "other" });
    expect(parseRef("   ")).toBeNull();
  });
});

describe("distill", () => {
  it("agrupa por modelo objetivo y separa campos, referencias y predicados", () => {
    const result = distill([
      anchor("anchor-1", "instructions", "(field ConversationStep instructions)", "cómo conduce el paso"),
      anchor("anchor-2", "grounded", "(relation grounded_by)", "el paso se apoya en un dominio"),
      anchor("anchor-3", "pago", '(where DomainAtom "se paga con transferencia")', "cómo se paga"),
    ]);
    const step = result.models.find((model) => model.model === "ConversationStep");
    const domain = result.models.find((model) => model.model === "DomainAtom");
    expect(step?.fields.map((field) => field.name)).toEqual(["instructions"]);
    expect(step?.references).toEqual([]);
    expect(result.models.find((model) => model.model === "grounded_by")?.references.map((p) => p.name)).toEqual(["grounded_by"]);
    expect(domain?.predicates.map((p) => p.name)).toEqual(["se paga con transferencia"]);
    expect(domain?.fields).toEqual([]);
  });

  it("cada campo arrastra el símbolo y el motive del anchor que lo originó", () => {
    const [draft] = distill([anchor("anchor-1", "instructions", "(field ConversationStep instructions)", "cómo conduce el paso")]).models;
    expect(draft?.fields[0]).toMatchObject({
      name: "instructions",
      role: "field",
      symbol: "instructions",
      motive: "cómo conduce el paso",
    });
    expect(draft?.fields[0]?.sources.map((source) => source.doc)).toEqual(["anchor-1"]);
  });

  it("un campo repetido es una propuesta con varios orígenes", () => {
    const [draft] = distill([
      anchor("anchor-1", "instructions", "(field ConversationStep instructions)", "primera razón"),
      anchor("anchor-2", "instructions-2", "(field ConversationStep instructions)", "segunda razón"),
    ]).models;
    expect(draft?.fields).toHaveLength(1);
    expect(draft?.fields[0]?.motive).toBe("primera razón");
    expect(draft?.fields[0]?.sources).toHaveLength(2);
  });

  it("un anchor sin motive no se propone: queda en unbacked", () => {
    const result = distill([anchor("anchor-1", "instructions", "(field ConversationStep instructions)", "   ")]);
    expect(result.models).toEqual([]);
    expect(result.unbacked.map((entry) => entry.doc)).toEqual(["anchor-1"]);
  });

  it("un ref irreconocible queda en unparsed, no se inventa un tipo", () => {
    const result = distill([anchor("anchor-1", "x", "lo que sea", "un motivo")]);
    expect(result.models).toEqual([]);
    expect(result.unparsed.map((entry) => entry.doc)).toEqual(["anchor-1"]);
  });

  it("un (model M) tipa pero no propone campo", () => {
    const result = distill([anchor("anchor-1", "atom", "(model DomainAtom)", "el atom de dominio")]);
    expect(result.models).toEqual([]);
    expect(result.unparsed).toEqual([]);
    expect(result.unbacked).toEqual([]);
  });

  it("propone __template__ solo con dos o más campos", () => {
    const one = distill([anchor("a", "s", "(field M uno)", "m")]).models[0];
    const two = distill([anchor("a", "s", "(field M uno)", "m"), anchor("b", "t", "(field M dos)", "m")]).models[0];
    expect(one?.template).toBeNull();
    expect(two?.template).toContain("uno: \u2e22rev\u2022uno\u2e25");
    expect(two?.template).toContain("dos: \u2e22rev\u2022dos\u2e25");
  });

  it("ordena los campos por cantidad de orígenes y el modelo por cantidad de campos", () => {
    const result = distill([
      anchor("a", "s", "(field Z uno)", "m"),
      anchor("b", "t", "(field Z dos)", "m"),
      anchor("c", "u", "(field Z dos)", "m"),
      anchor("d", "v", "(field A solo)", "m"),
    ]);
    expect(result.models.map((model) => model.model)).toEqual(["Z", "A"]);
    expect(result.models[0]?.fields.map((field) => field.name)).toEqual(["dos", "uno"]);
  });
});

describe("suggestTemplate", () => {
  it("sin campos no propone nada", () => {
    expect(suggestTemplate([])).toBeNull();
  });
});

describe("collectAnchors", () => {
  const doc = (id: string, model: string, payload: Record<string, unknown>): GraphDocument => ({ id, model_name: model, path: `${model}/${id}.md`, payload });

  it("filtra por el modelo de anchors y exige ref", () => {
    const docs = [
      doc("anchor-1", "AnchorDoc", { symbol: "s", ref: "(model M)", motive: "m" }),
      doc("anchor-2", "AnchorDoc", { symbol: "s", motive: "sin ref" }),
      doc("domain-1", "DomainAtom", { ref: "(model M)" }),
    ];
    const entries = collectAnchors(docs, "AnchorDoc");
    expect(entries.map((entry) => entry.doc)).toEqual(["anchor-1"]);
  });

  it("sin modelo resuelto cae al nombre de modelo que se parece a anchor", () => {
    const docs = [doc("anchor-1", "Alias", { ref: "(model M)" }), doc("x", "DomainAtom", { ref: "(model M)" })];
    expect(collectAnchors(docs, null)).toEqual([]);
    expect(collectAnchors([doc("anchor-1", "AnchorAlias", { ref: "(model M)" })], null)).toHaveLength(1);
  });
});

const fieldHit = (name: string, field: string, score: number): FieldRankHit => ({
  id: `docs/M/${name}/${field}`,
  document_id: `M:${name}`,
  field,
  model: "M",
  name,
  score,
  text: "t",
  payload: {},
  tags: [],
});

describe("deduplicación de campos propuestos", () => {
  it("la consulta sale del motive, acotada; sin motive no hay consulta", () => {
    expect(similarityQuery({ motive: "  el   cliente\nno quiere " })).toBe("el cliente no quiere");
    expect(similarityQuery({ motive: "   " })).toBeNull();
    expect(similarityQuery({ motive: "x".repeat(1000) })?.length).toBe(400);
  });

  it("among excluye los propios anchors y usa Model:name", () => {
    const docs = [
      { id: "anchor-a", model_name: "AnchorDoc", path: "", payload: {} },
      { id: "acta", model_name: "ActaDoc", path: "", payload: {} },
    ] as GraphDocument[];
    expect(amongIds(docs, [anchor("anchor-a", "s", "(field M f)", "m")])).toEqual(["ActaDoc:acta"]);
  });

  it("rankRequest usa fields, k=2 y umbral; sin among si no entra o está vacío", () => {
    expect(rankRequest("q", ["A:a"])).toMatchObject({ q: "q", fields: true, k: SIMILAR_K, among: ["A:a"], threshold: 0.35 });
    const long = Array.from({ length: AMONG_MAX_CHARS }, (_, i) => `M:doc${i}`);
    const wide = rankRequest("q", long);
    expect(wide.among).toBeUndefined();
    expect(wide.k).toBe(SIMILAR_K_UNSCOPED);
    expect(rankRequest("q", []).among).toBeUndefined();
  });

  it("clasifica duplicado/parecido, ordena, descarta propios y bajos", () => {
    const hits = [fieldHit("b", "f", 0.5), fieldHit("own", "motive", 1), fieldHit("a", "f", 0.9), fieldHit("c", "f", 0.2), fieldHit("d", "f", 0.4)];
    const out = classifyMatches(hits, new Set(["own"]));
    expect(out.map((m) => [m.hit.name, m.kind])).toEqual([
      ["a", "duplicate"],
      ["b", "similar"],
    ]);
    expect(classifyMatches([], new Set())).toEqual([]);
    expect(classifyMatches([fieldHit("a", "f", 0.85)], new Set())[0]?.kind).toBe("duplicate");
  });
});
