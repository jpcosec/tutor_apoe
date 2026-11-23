import { describe, expect, it } from "vitest";
import { checkSelection, effectiveRange, paragraphsOf, pointOffset, segmentBody } from "./atom-text";

const BODY = "Uno dos tres.\n\nCuatro cinco.\n\nSeis.";

describe("paragraphsOf", () => {
  it("parte por \\n\\n con offsets globales", () => {
    expect(paragraphsOf(BODY)).toEqual([
      { start: 0, end: 13, text: "Uno dos tres." },
      { start: 15, end: 28, text: "Cuatro cinco." },
      { start: 30, end: 35, text: "Seis." },
    ]);
  });
  it("omite párrafos vacíos y conserva los offsets", () => {
    expect(paragraphsOf("a\n\n\n\nb").map((p) => [p.start, p.end])).toEqual([[0, 1], [5, 6]]);
  });
});

describe("segmentBody", () => {
  it("sin átomos: un segmento por párrafo", () => {
    const [p] = segmentBody("hola", []);
    expect(p!.segments).toEqual([{ start: 0, end: 4, text: "hola", atomIds: [] }]);
  });
  it("corta en todos los bordes y apila átomos solapados", () => {
    const [p] = segmentBody(BODY, [
      { id: "a", start: 0, end: 7 },
      { id: "b", start: 4, end: 13 },
    ]);
    expect(p!.segments.map((s) => [s.text, s.atomIds])).toEqual([
      ["Uno ", ["a"]],
      ["dos", ["a", "b"]],
      [" tres.", ["b"]],
    ]);
  });
  it("un rango que cruza párrafos se parte y nunca cubre el \\n\\n", () => {
    const paras = segmentBody(BODY, [{ id: "x", start: 10, end: 20 }]);
    expect(paras[0]!.segments.map((s) => [s.text, s.atomIds])).toEqual([["Uno dos tr", []], ["es.", ["x"]]]);
    expect(paras[1]!.segments.map((s) => [s.text, s.atomIds])).toEqual([["Cuatr", ["x"]], ["o cinco.", []]]);
    expect(paras.flatMap((p) => p.segments).some((s) => s.text.includes("\n"))).toBe(false);
  });
  it("rango que empieza o termina dentro del separador se recorta al párrafo", () => {
    const paras = segmentBody(BODY, [{ id: "x", start: 13, end: 16 }]);
    expect(paras[0]!.segments.every((s) => s.atomIds.length === 0)).toBe(true);
    expect(paras[1]!.segments[0]).toMatchObject({ text: "C", atomIds: ["x"] });
  });
  it("los segmentos reconstruyen cada párrafo", () => {
    const paras = segmentBody(BODY, [{ id: "a", start: 2, end: 30 }, { id: "b", start: 16, end: 33 }]);
    for (const p of paras) expect(p.segments.map((s) => s.text).join("")).toBe(p.text);
  });
});

describe("effectiveRange", () => {
  const body = "xx la cita exacta yy";
  it("intacto usa start/end", () => {
    expect(effectiveRange(body, { id: "a", start: 3, end: 17, quote: "la cita exacta" })).toEqual({ id: "a", start: 3, end: 17 });
  });
  it("movido usa la posición reparada", () => {
    expect(effectiveRange(body, { id: "a", start: 0, end: 14, quote: "la cita exacta" })).toEqual({ id: "a", start: 3, end: 17 });
  });
  it("huérfano no tiene rango", () => {
    expect(effectiveRange(body, { id: "a", start: 0, end: 5, quote: "no está" })).toBeNull();
  });
});

describe("checkSelection", () => {
  it("acepta un tramo dentro de un párrafo", () => {
    expect(checkSelection(BODY, 4, 7)).toEqual({ ok: true, from: 4, to: 7 });
    expect(checkSelection(BODY, 7, 4)).toEqual({ ok: true, from: 4, to: 7 });
  });
  it("rechaza vacío y solo espacios", () => {
    expect(checkSelection(BODY, 4, 4).ok).toBe(false);
    expect(checkSelection(BODY, 3, 4).ok).toBe(false);
  });
  it("rechaza cruzar párrafos", () => {
    const r = checkSelection(BODY, 10, 20);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toMatch(/párrafo/);
  });
});

describe("pointOffset", () => {
  it("suma el inicio del segmento", () => expect(pointOffset(15, 3)).toBe(18));
});
