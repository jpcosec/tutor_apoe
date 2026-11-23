import { describe, expect, it } from "vitest";
import { above, byScore, docIdOf, fieldLabel, queryText, similarityNotice } from "./similarity";

describe("similarity", () => {
  it("acota y normaliza la consulta", () => {
    expect(queryText("  hola \n\n  mundo ")).toBe("hola mundo");
    expect(queryText("x".repeat(500))).toHaveLength(400);
    expect(queryText("   ")).toBe("");
  });
  it("ordena sin mutar y filtra por umbral", () => {
    const hits = [{ score: 0.2 }, { score: 0.9 }, { score: 0.5 }];
    expect(byScore(hits).map((h) => h.score)).toEqual([0.9, 0.5, 0.2]);
    expect(hits[0]!.score).toBe(0.2);
    expect(above(hits, 0.5).map((h) => h.score)).toEqual([0.9, 0.5]);
  });
  it("etiquetas", () => {
    expect(docIdOf({ name: "pan" })).toBe("pan");
    expect(fieldLabel({ name: "pan", field: "title" })).toBe("pan/title");
  });
  it("solo los estados que no son resultado tienen aviso; la lista vacía no", () => {
    expect(similarityNotice({ status: "ok", hits: [] })).toBeNull();
    expect(similarityNotice(null)).toBeNull();
    expect(similarityNotice({ status: "not_indexed" })).toMatch(/no está indexado/);
    expect(similarityNotice({ status: "unavailable", reason: "404" })).toBe("Similitud no disponible: 404.");
  });
});
