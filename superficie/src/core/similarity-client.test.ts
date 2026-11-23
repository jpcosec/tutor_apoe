import { describe, expect, it, vi } from "vitest";
import { createHttpClient } from "./client";

const reply = (status: number, body: unknown) => vi.fn(async (_url: string, _init?: RequestInit) => new Response(JSON.stringify(body), { status }));

describe("cliente de similitud: tres estados que no se mezclan", () => {
  it("ok con hits", async () => {
    const f = reply(200, { hits: [{ id: "NoteDoc:pan", score: 0.75 }] });
    const r = await createHttpClient("/sldb", f).rank({ q: "pan", k: 3, threshold: 0.5, among: ["a", "b"], refresh: true });
    expect(r).toEqual({ status: "ok", hits: [{ id: "NoteDoc:pan", score: 0.75 }] });
    expect(f.mock.calls[0]![0]).toBe("/sldb/corpus/rank?q=pan&k=3&threshold=0.5&among=a%2Cb&refresh=1");
  });

  it("ok con lista vacía es 'sin parecidos', distinto de no indexado y de no disponible", async () => {
    expect(await createHttpClient("/sldb", reply(200, { hits: [] })).rank({ q: "x" })).toEqual({ status: "ok", hits: [] });
  });

  it("409 not_indexed", async () => {
    const r = await createHttpClient("/sldb", reply(409, { ok: false, error: "corpus no indexado", kind: "not_indexed" })).rank({ q: "x" });
    expect(r).toEqual({ status: "not_indexed" });
  });

  it("404, otro 409, cuerpo raro y fallo de red son 'unavailable' con su razón", async () => {
    const c404 = await createHttpClient("/sldb", reply(404, { ok: false, error: "Unknown route: /corpus/rank" })).rank({ q: "x" });
    expect(c404).toEqual({ status: "unavailable", reason: "Unknown route: /corpus/rank" });
    expect((await createHttpClient("/sldb", reply(409, { ok: false, error: "conflicto" })).rank({ q: "x" })).status).toBe("unavailable");
    expect((await createHttpClient("/sldb", reply(200, { nada: 1 })).rank({ q: "x" })).status).toBe("unavailable");
    const down = vi.fn(async () => { throw new Error("ECONNREFUSED"); });
    expect(await createHttpClient("/sldb", down).rank({ q: "x" })).toEqual({ status: "unavailable", reason: "ECONNREFUSED" });
  });

  it("fields=1 pide campos", async () => {
    const f = reply(200, { hits: [{ id: "docs/NoteDoc/pan/title", document_id: "NoteDoc:pan", field: "title", score: 1 }] });
    const r = await createHttpClient("/sldb", f).rank({ q: "pan", fields: true });
    expect(r.status).toBe("ok");
    expect(String(f.mock.calls[0]![0])).toContain("fields=1");
  });

  it("similar: pares [nodo, compartidos]; 404 de nodo desconocido es unavailable", async () => {
    const f = reply(200, { similar: [["sldb://document/ItemDoc:i1", 2]] });
    expect(await createHttpClient("/sldb", f).similar("NoteDoc:n1", { limit: 5, types: ["ItemDoc"] })).toEqual({ status: "ok", hits: [["sldb://document/ItemDoc:i1", 2]] });
    expect(String(f.mock.calls[0]![0])).toBe("/sldb/similar?id=NoteDoc%3An1&limit=5&types=ItemDoc");
    expect((await createHttpClient("/sldb", reply(404, { ok: false, error: "Unknown node: X" })).similar("X")).status).toBe("unavailable");
  });
});
