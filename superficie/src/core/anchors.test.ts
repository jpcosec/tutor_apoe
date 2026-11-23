import { describe, expect, it } from "vitest";
import type { SchemaModel } from "./contract";
import {
  anchorIdFor,
  buildPayload,
  classifyHits,
  duplicateQuery,
  duplicateRankParams,
  scorePercent,
  draftFromSelection,
  findAnchorModel,
  inputForField,
  lineLabel,
  lineOf,
  selectionAt,
  shortenQuote,
  slugify,
  splitByAnchors,
  suggestSymbol,
  toStringList,
  validateDraft,
  type SessionAnchor,
} from "./anchors";

/**
 * Modelo como el que registra este store: `pron.models:AnchorDoc`, sin
 * kind/tags/provenance. `ref` sin `pattern` (el schema real tampoco lo trae).
 */
const anchorDoc: SchemaModel = {
  id: "AnchorDoc",
  model_ref: "pron.models:AnchorDoc",
  fields: [
    { name: "symbol", kind: "string", required: true },
    { name: "forms", kind: "stringlist", required: false },
    { name: "ref", kind: "string", required: true },
    { name: "steps", kind: "list", required: false },
    { name: "motive", kind: "string", required: true },
  ],
};

describe("lineOf", () => {
  it("cuenta líneas 1-based", () => {
    const text = "uno\ndos\ntres";
    expect(lineOf(text, 0)).toBe(1);
    expect(lineOf(text, 3)).toBe(1); // el \n pertenece al final de la línea 1
    expect(lineOf(text, 4)).toBe(2);
    expect(lineOf(text, text.length)).toBe(3);
  });

  it("clampea índices fuera del texto", () => {
    expect(lineOf("a", -5)).toBe(1);
    expect(lineOf("a", 99)).toBe(1);
  });
});

describe("selectionAt", () => {
  const text = "el cliente manifiesta que no será\nposible una conexión directa a SAP.\n\nEl plazo es de 24 horas.";

  it("devuelve la cita exacta y las líneas del tramo", () => {
    const start = text.indexOf("no será");
    const end = text.indexOf("SAP.") + "SAP.".length;
    const selection = selectionAt(text, start, end);
    expect(selection).not.toBeNull();
    expect(selection?.quote).toBe("no será\nposible una conexión directa a SAP.");
    expect(selection?.startLine).toBe(1);
    expect(selection?.endLine).toBe(2);
    expect(lineLabel(selection!)).toBe("líneas 1–2");
  });

  it("una selección de una sola línea usa el singular", () => {
    const selection = selectionAt(text, 0, 2);
    expect(selection?.startLine).toBe(1);
    expect(selection?.endLine).toBe(1);
    expect(lineLabel(selection!)).toBe("línea 1");
  });

  it("un tramo vacío no es selección", () => {
    expect(selectionAt(text, 3, 3)).toBeNull();
    expect(selectionAt(text, 8, 2)).toBeNull();
  });

  it("clampea el fin al largo del texto", () => {
    const selection = selectionAt(text, 0, text.length + 500);
    expect(selection?.end).toBe(text.length);
  });
});

describe("slugify / suggestSymbol / anchorIdFor", () => {
  it("saca acentos, colapsa separadores y recorta los extremos", () => {
    expect(slugify("  Conexión DIRECTA, a SAP!! ")).toBe("conexion-directa-a-sap");
    expect(slugify("--")).toBe("");
  });

  it("sugiere un símbolo corto desde la selección", () => {
    expect(suggestSymbol("No será posible una conexión directa a SAP")).toBe("no-sera-posible-una");
    expect(suggestSymbol("Reservas", 2)).toBe("reservas");
    expect(suggestSymbol("....")).toBe("");
  });

  it("acota el símbolo a 60 caracteres sin cortar en guion", () => {
    const symbol = suggestSymbol("a".repeat(40) + " " + "b".repeat(40), 4);
    expect(symbol.length).toBeLessThanOrEqual(60);
    expect(symbol.endsWith("-")).toBe(false);
  });

  it("arma el id anchor-<symbol> y no duplica el prefijo", () => {
    expect(anchorIdFor("Sin conexión SAP")).toBe("anchor-sin-conexion-sap");
    expect(anchorIdFor("anchor-sin-conexion-sap")).toBe("anchor-sin-conexion-sap");
    expect(anchorIdFor("Anchor: Reservas")).toBe("anchor-reservas");
  });
});

describe("findAnchorModel", () => {
  it("prefiere AnchorDoc", () => {
    const other: SchemaModel = { id: "Otro", model_ref: "x:Otro", fields: [] };
    expect(findAnchorModel([other, anchorDoc])?.id).toBe("AnchorDoc");
  });

  it("cae a la variante que el store registre", () => {
    const variant: SchemaModel = { id: "Alias", model_ref: "sldb.models.anchor_doc:Alias", fields: [] };
    expect(findAnchorModel([variant])?.id).toBe("Alias");
  });

  it("sin modelo de anchors devuelve null", () => {
    expect(findAnchorModel([{ id: "DomainAtom", model_ref: "kb:DomainAtom", fields: [] }])).toBeNull();
  });
});

describe("inputForField", () => {
  it("mapea cada kind a su control", () => {
    expect(inputForField({ name: "symbol", kind: "string", required: true })).toBe("text");
    expect(inputForField({ name: "motive", kind: "string", required: true })).toBe("textarea");
    expect(inputForField({ name: "forms", kind: "stringlist", required: false })).toBe("json");
    expect(inputForField({ name: "steps", kind: "list", required: false })).toBe("json");
    expect(inputForField({ name: "kind", kind: "enum", required: true, enum: ["model"] })).toBe("select");
    expect(inputForField({ name: "n", kind: "integer", required: false })).toBe("number");
    expect(inputForField({ name: "b", kind: "boolean", required: false })).toBe("boolean");
  });
});

describe("toStringList", () => {
  it("acepta lista por comas y JSON array", () => {
    expect(toStringList("reserva, reservas")).toEqual(["reserva", "reservas"]);
    expect(toStringList('["a","b"]')).toEqual(["a", "b"]);
    expect(toStringList("")).toEqual([]);
  });
});

describe("validateDraft", () => {
  const draft = (over: Record<string, string> = {}): Record<string, string> => ({
    symbol: "reserva",
    ref: "(model DomainAtom)",
    motive: "una reserva",
    ...over,
  });

  it("exige los campos requeridos", () => {
    const errors = validateDraft(draft({ symbol: "  ", motive: "" }), anchorDoc);
    expect(errors.map((error) => error.field).sort()).toEqual(["motive", "symbol"]);
  });

  it("acepta un draft completo", () => {
    expect(validateDraft(draft(), anchorDoc)).toEqual([]);
  });

  it("usa el pattern que declara el schema, no uno propio", () => {
    const withPattern: SchemaModel = {
      ...anchorDoc,
      fields: anchorDoc.fields.map((field) => (field.name === "ref" ? { ...field, pattern: "^\\(model .+\\)$" } : field)),
    };
    expect(validateDraft(draft(), withPattern)).toEqual([]);
    const errors = validateDraft(draft({ ref: "model:DomainAtom" }), withPattern);
    expect(errors).toHaveLength(1);
    expect(errors[0]?.message).toContain("^\\(model .+\\)$");
  });

  it("un pattern inválido del store no bloquea el formulario", () => {
    const broken: SchemaModel = {
      ...anchorDoc,
      fields: anchorDoc.fields.map((field) => (field.name === "ref" ? { ...field, pattern: "([unclosed" } : field)),
    };
    expect(validateDraft(draft(), broken)).toEqual([]);
  });

  it("rechaza JSON inválido en list", () => {
    const errors = validateDraft(draft({ steps: "{no json" }), anchorDoc);
    expect(errors.map((error) => error.field)).toEqual(["steps"]);
  });

  it("valida enum, entero, número y booleano", () => {
    const model: SchemaModel = {
      id: "M",
      model_ref: "m:M",
      fields: [
        { name: "kind", kind: "enum", required: true, enum: ["model", "doc"] },
        { name: "n", kind: "integer", required: false },
        { name: "x", kind: "number", required: false },
        { name: "flag", kind: "boolean", required: false },
      ],
    };
    expect(validateDraft({ kind: "model", n: "3", x: "1.5", flag: "true" }, model)).toEqual([]);
    expect(validateDraft({ kind: "otro", n: "3.5", x: "no", flag: "sí" }, model).map((error) => error.field).sort()).toEqual([
      "flag",
      "kind",
      "n",
      "x",
    ]);
  });
});

describe("buildPayload", () => {
  it("incluye SOLO los campos que el modelo declara", () => {
    const { payload, errors } = buildPayload(
      { symbol: "reserva", ref: "(model DomainAtom)", motive: "una reserva", kind: "model", provenance: "x.md", extra: "no" },
      anchorDoc,
    );
    expect(errors).toEqual([]);
    expect(Object.keys(payload).sort()).toEqual(["motive", "ref", "symbol"]);
  });

  it("omite opcionales vacíos y convierte los declarados", () => {
    const { payload } = buildPayload({ symbol: "reserva", ref: "(model DomainAtom)", motive: "m", forms: "a, b", steps: '[{"do":"x"}]' }, anchorDoc);
    expect(payload).toEqual({ symbol: "reserva", ref: "(model DomainAtom)", motive: "m", forms: ["a", "b"], steps: [{ do: "x" }] });
  });

  it("no construye nada si hay errores", () => {
    const { payload, errors } = buildPayload({ symbol: "reserva" }, anchorDoc);
    expect(payload).toEqual({});
    expect(errors.map((error) => error.field).sort()).toEqual(["motive", "ref"]);
  });

  it("funciona con la variante que trae kind/tags/provenance", () => {
    const variant: SchemaModel = {
      id: "Alias",
      model_ref: "sldb.models.anchor_doc:Alias",
      fields: [
        { name: "symbol", kind: "string", required: true },
        { name: "kind", kind: "enum", required: true, enum: ["model", "doc"] },
        { name: "ref", kind: "string", required: true },
        { name: "motive", kind: "string", required: true },
        { name: "tags", kind: "stringlist", required: false },
        { name: "provenance", kind: "string", required: false },
      ],
    };
    const { payload, errors } = buildPayload({ symbol: "reserva", kind: "model", ref: "(model DomainAtom)", motive: "m", tags: "a:1, b:2", provenance: "" }, variant);
    expect(errors).toEqual([]);
    expect(payload).toEqual({ symbol: "reserva", kind: "model", ref: "(model DomainAtom)", motive: "m", tags: ["a:1", "b:2"] });
  });
});

describe("draftFromSelection", () => {
  it("sugiere el símbolo y deja el resto vacío", () => {
    const selection = selectionAt("no será posible una conexión directa a SAP", 0, 30)!;
    expect(draftFromSelection(anchorDoc, selection)).toEqual({
      symbol: "no-sera-posible-una",
      forms: "",
      ref: "",
      steps: "",
      motive: "",
    });
  });
});

describe("splitByAnchors", () => {
  const anchor = (id: string, start: number, end: number): SessionAnchor => ({
    id,
    symbol: id.replace(/^anchor-/, ""),
    quote: "",
    start,
    end,
    startLine: 1,
    endLine: 1,
  });

  it("corta el texto en tramos marcados y literales", () => {
    const runs = splitByAnchors("abcdef", [anchor("anchor-a", 1, 3)]);
    expect(runs.map((run) => [run.text, run.anchor?.id ?? null])).toEqual([
      ["a", null],
      ["bc", "anchor-a"],
      ["def", null],
    ]);
  });

  it("sin anchors devuelve el texto entero", () => {
    expect(splitByAnchors("abc", []).map((run) => run.text)).toEqual(["abc"]);
  });

  it("descarta el que pisa a otro y los rangos inválidos", () => {
    const runs = splitByAnchors("abcdef", [anchor("anchor-a", 1, 4), anchor("anchor-b", 2, 6), anchor("anchor-c", 9, 12)]);
    expect(runs.filter((run) => run.anchor).map((run) => run.anchor?.id)).toEqual(["anchor-a"]);
  });

  it("tolera anchors fuera de orden", () => {
    const runs = splitByAnchors("abcdef", [anchor("anchor-b", 4, 6), anchor("anchor-a", 0, 2)]);
    expect(runs.filter((run) => run.anchor).map((run) => run.anchor?.id)).toEqual(["anchor-a", "anchor-b"]);
  });
});

describe("shortenQuote", () => {
  it("aplana espacios y recorta", () => {
    expect(shortenQuote("  hola \n  mundo  ")).toBe("hola mundo");
    expect(shortenQuote("1234567", 5)).toBe("12345…");
  });
});

describe("aviso de duplicados (puro)", () => {
  const h = (name: string, score: number) => ({ id: name, document_id: name, field: "quote", model: "M", name, score, text: "", payload: {}, tags: [] });

  it("no consulta con texto corto o vacío y acota/normaliza el largo", () => {
    expect(duplicateQuery(null)).toBeNull();
    expect(duplicateQuery("  corto  ")).toBeNull();
    expect(duplicateQuery("una   frase\n con espacios de sobra")).toBe("una frase con espacios de sobra");
    expect(duplicateQuery("x".repeat(1000))?.length).toBe(400);
  });

  it("arma los parámetros: k 3, umbral de sugerencia, refresh solo si se pide", () => {
    expect(duplicateRankParams("q")).toEqual({ q: "q", k: 3, threshold: 0.35, fields: true, refresh: false });
    expect(duplicateRankParams("q", true)).toMatchObject({ refresh: true, fields: true });
  });

  it("clasifica en duplicado y parecido, mejores primero, y descarta lo bajo el umbral", () => {
    const { duplicates, similar } = classifyHits([h("a", 0.5), h("b", 0.9), h("c", 0.1), h("d", 0.85), h("e", 0.4)]);
    expect(duplicates.map((x) => x.name)).toEqual(["b", "d"]);
    expect(similar.map((x) => x.name)).toEqual(["a"]);
    expect(classifyHits([h("a", 0.5), h("c", 0.1)]).similar.map((x) => x.name)).toEqual(["a"]);
    expect(classifyHits([])).toEqual({ duplicates: [], similar: [] });
  });

  it("puntaje a porcentaje entero", () => {
    expect(scorePercent(0.914)).toBe(91);
    expect(scorePercent(1.2)).toBe(100);
  });
});
