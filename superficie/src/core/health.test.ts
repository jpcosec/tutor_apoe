import { describe, expect, it, vi } from "vitest";
import type { DocumentSegments, GraphDocument, Segment } from "./contract";
import { SldbHttpError, type SldbClient } from "./client";
import { collectHealth, storeDivergences, undeclaredHeadings } from "./health";

const doc: GraphDocument = { id: "spec", model_name: "DomainAtom", path: "domain/spec.md", payload: {} };

const field = (path: string, marker: string, text: string, children: Segment[] = []): Segment =>
  ({ type: "field", path, marker, text, start: 0, end: text.length, traits: [], editable: marker !== "render", display: "block", source: null, children }) as Segment;

const literal = (text: string): Segment =>
  ({ type: "literal", text, start: 0, end: text.length }) as Segment;

const segments = (tree: Segment[], canonical: boolean | null = true): DocumentSegments =>
  ({ id: "spec", doc: "spec", model: "DomainAtom", path: "domain/spec.md", text: "", canonical, payload: {}, segments: tree });

describe("undeclaredHeadings", () => {
  it("cuenta los headings dentro del valor de un field rev, no los del template", () => {
    const data = segments([
      literal("# "),
      field("title", "render", "Spec de cobranza"),
      literal("\n\n## Answer\n\n"),
      field("answer", "rev", "intro\n\n## Entidades\n\ntexto\n\n## Herramientas trazadas\n\nmás"),
    ]);
    expect(undeclaredHeadings(data)).toEqual(["Entidades", "Herramientas trazadas"]);
  });

  it("encuentra headings anidados y en optrev, y acepta todos los niveles", () => {
    const data = segments([
      field("body", "optrev", "### Medición 1 — consultable\n\n#### detalle"),
      field("outer", "rev", "", [field("inner", "optrev", "## Consultas de verificación (M1)")]),
    ]);
    expect(undeclaredHeadings(data)).toEqual(["Medición 1 — consultable", "detalle", "Consultas de verificación (M1)"]);
  });

  it("ignora `#` sin espacio y los fields no editables", () => {
    const data = segments([
      field("render_field", "render", "# no cuenta"),
      field("answer", "rev", "#nohesheading\nlínea normal"),
    ]);
    expect(undeclaredHeadings(data)).toEqual([]);
  });
});

describe("collectHealth", () => {
  const clientWith = (segments: SldbClient["segments"]) => ({ segments } as unknown as SldbClient);

  it("clasifica ruido estructural, no canónico y errores de schema", async () => {
    const client = clientWith(
      vi.fn(async () => segments([field("answer", "rev", "## Entidades\n\ntexto")], false)) as unknown as SldbClient["segments"],
    );
    const report = await collectHealth(client, [doc], [{ model: "DomainAtom", error: "x" }]);

    expect(report.checked).toBe(1);
    expect(report.structural).toEqual([{ doc: "spec", model: "DomainAtom", path: "domain/spec.md", headings: ["Entidades"] }]);
    expect(report.noncanonical.map((f) => f.doc)).toEqual(["spec"]);
    expect(report.unreadable).toEqual([]);
    expect(report.modelErrors).toEqual([{ model: "DomainAtom", error: "x" }]);
  });

  it("no marca ruido cuando no hay headings dentro de fields", async () => {
    const client = clientWith(vi.fn(async () => segments([field("answer", "rev", "solo prosa")])) as unknown as SldbClient["segments"]);
    const report = await collectHealth(client, [doc]);
    expect(report.structural).toEqual([]);
    expect(report.noncanonical).toEqual([]);
  });

  it("documentos ilegibles no se presentan como ruido estructural", async () => {
    const client = clientWith(
      vi.fn(async () => {
        throw new SldbHttpError("SLDB respondió 422", 422, null);
      }) as unknown as SldbClient["segments"],
    );
    const report = await collectHealth(client, [doc]);
    expect(report.structural).toEqual([]);
    expect(report.unreadable).toEqual([{ doc: "spec", model: "DomainAtom", path: "domain/spec.md", detail: "SLDB respondió 422" }]);
  });
});

describe("storeDivergences (/stores/check)", () => {
  const doc = { name: "a", path: "a.md", path_exists: true, hash_c_ok: true, hash_d_ok: true, content_ok: true, fields_ok: true, note: "ok", explain: "ok" };
  const model = { name: "M", hash_b_ok: true, roster_ok: true, contract_ok: true, roster_only_failure: false, documents: [doc] };
  const check = { ok: true, valid: true, root_ok: true, hash_a_ok: true, summary: "PASS", checked: 1, damaged: [], reformatted: [], models: [model] };

  it("un store sano no tiene divergencias", () => {
    expect(storeDivergences(check)).toEqual([]);
  });

  it("distingue archivo borrado, editado fuera de SLDB y campos distintos", () => {
    const models = [{ ...model, documents: [
      { ...doc, name: "borrado", path_exists: false, content_ok: false, explain: "missing" },
      { ...doc, name: "editado", content_ok: false, explain: "changed" },
      { ...doc, name: "campos", fields_ok: false, explain: "" },
    ] }];
    const kinds = storeDivergences({ ...check, ok: false, valid: false, models }).map((d) => [d.doc, d.kind]);
    expect(kinds).toEqual([["borrado", "archivo-borrado"], ["editado", "contenido"], ["campos", "campos"]]);
  });

  it("contrato, roster y raíz son divergencias del modelo o del store, no de un documento", () => {
    const bad = { ...check, root_ok: false, models: [{ ...model, contract_ok: false, roster_ok: false }] };
    expect(storeDivergences(bad).map((d) => d.kind)).toEqual(["raiz", "contrato", "roster"]);
  });
});
