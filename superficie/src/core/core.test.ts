import { describe, expect, it, vi } from "vitest";
import type { DocumentSegments } from "./contract";
import { createHttpClient, SaveConflictError, SldbHttpError } from "./client";
import { FieldColors } from "./colors";
import { fieldRoots, layoutSegments } from "./layout";
import { getAt, insertAt, listItemOf, moveAt, removeAt, setAt } from "./paths";
import semaforo from "./__fixtures__/semaforo.segments.json";
import sap from "./__fixtures__/sap.segments.json";
import acuerdos from "./__fixtures__/acuerdos.segments.json";
import nota from "./__fixtures__/reunion-12.segments.json";

const doc = (raw: unknown) => raw as DocumentSegments;

describe("paths", () => {
  const payload = { title: "a", tags: ["x", "y"], rows: [{ c: 1 }] };

  it("lee y escribe por dirección sin mutar", () => {
    const next = setAt(payload, "rows/0/c", 2);
    expect(getAt(next, "rows/0/c")).toBe(2);
    expect(getAt(payload, "rows/0/c")).toBe(1);
  });

  it("opera listas", () => {
    expect(getAt(insertAt(payload, "tags", 1, "z"), "tags")).toEqual(["x", "z", "y"]);
    expect(getAt(removeAt(payload, "tags", 0), "tags")).toEqual(["y"]);
    expect(getAt(moveAt(payload, "tags", 0, 1), "tags")).toEqual(["y", "x"]);
    expect(listItemOf("tags/3")).toEqual({ list: "tags", index: 3 });
    expect(listItemOf("title")).toBeNull();
  });
});

describe("layout sobre segmentos reales", () => {
  it("frontmatter como propiedades, título como heading, bloques y listas", () => {
    const units = layoutSegments(doc(sap).segments);
    const [front, heading] = units;
    expect(front?.unit).toBe("frontmatter");
    if (front?.unit === "frontmatter") expect(front.rows.map((r) => r.key)).toEqual(["status", "owner"]);
    expect(heading).toMatchObject({ unit: "line", kind: { type: "heading", level: 1 } });
    const blocks = units.filter((u) => u.unit === "block").map((u) => (u.unit === "block" ? u.segment.path : ""));
    expect(blocks).toEqual(["context", "decision", "alternatives"]);
    const list = units.find((u) => u.unit === "list");
    expect(list).toMatchObject({ listPath: "tags" });
  });

  it("el documento libre es un único bloque", () => {
    const units = layoutSegments(doc(nota).segments);
    expect(units).toHaveLength(1);
    expect(units[0]).toMatchObject({ unit: "block", segment: { path: "body" } });
  });

  it("la composición expone piezas con su documento de origen", () => {
    const composed = layoutSegments(doc(acuerdos).segments).find((u) => u.unit === "block" && u.segment.composition);
    expect(composed?.unit).toBe("block");
    if (composed?.unit !== "block") return;
    const pieces = composed.segment.children.filter((c) => c.type === "composition");
    expect(pieces.map((p) => p.source?.doc)).toEqual(["sap", "semaforo"]);
    const inner = layoutSegments(pieces[0]!.children);
    expect(inner[0]).toMatchObject({ unit: "line", kind: { type: "heading", level: 3 } });
  });

  it("el optrev presente queda como propiedad", () => {
    const [front] = layoutSegments(doc(semaforo).segments);
    if (front?.unit === "frontmatter") expect(front.rows.map((r) => r.key)).toContain("review");
  });

  it("los colores siguen el orden de aparición", () => {
    const colors = new FieldColors(fieldRoots(doc(sap).segments));
    expect(colors.slotOf("status")).toBe(0);
    expect(colors.slotOf("owner")).toBe(1);
    expect(FieldColors.keyFor("tags/1")).toBe("tags");
    expect(FieldColors.keyFor("title", "sap")).toBe("sap#title");
  });
});

describe("cliente", () => {
  it("traduce 409 a SaveConflictError", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ ok: false, error: "cambió" }), { status: 409 }));
    const client = createHttpClient("/sldb", fetchImpl);
    await expect(client.save([])).rejects.toBeInstanceOf(SaveConflictError);
    expect(fetchImpl).toHaveBeenCalledWith("/sldb/save", expect.objectContaining({ method: "POST" }));
  });

  it("getEdges pide /edges con y sin id", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ edges: [{ id: "e1" }] }), { status: 200 }));
    const client = createHttpClient("/sldb", fetchImpl);
    expect(await client.getEdges()).toEqual([{ id: "e1" }]);
    await client.getEdges("AtomDoc:a1");
    expect(fetchImpl).toHaveBeenNthCalledWith(1, "/sldb/edges", undefined);
    expect(fetchImpl).toHaveBeenNthCalledWith(2, "/sldb/edges?id=AtomDoc%3Aa1", undefined);
  });

  it("createDocument hace POST /docs y traduce errores", async () => {
    const ok = vi.fn(async () => new Response(JSON.stringify({ ok: true, id: "AtomDoc:a7", version: "v1" }), { status: 200 }));
    const res = await createHttpClient("/sldb", ok).createDocument("AtomDoc", "a7", { kind: "hecho" });
    expect(res).toEqual({ ok: true, id: "AtomDoc:a7", version: "v1" });
    expect(ok).toHaveBeenCalledWith("/sldb/docs", expect.objectContaining({ method: "POST", body: JSON.stringify({ model: "AtomDoc", name: "a7", payload: { kind: "hecho" } }) }));
    const bad = vi.fn(async () => new Response(JSON.stringify({ ok: false, error: "payload inválido" }), { status: 422 }));
    await expect(createHttpClient("/sldb", bad).createDocument("AtomDoc", "a8", {})).rejects.toMatchObject({ message: "payload inválido", status: 422 });
    const dup = vi.fn(async () => new Response(JSON.stringify({ ok: false, error: "ya existe" }), { status: 409 }));
    await expect(createHttpClient("/sldb", dup).createDocument("AtomDoc", "a1", {})).rejects.toBeInstanceOf(SldbHttpError);
  });

  it("edicion de MachineDoc: manda expected (cerrojo optimista) y traduce 409 a SaveConflictError", async () => {
    const base = {
      title: "Consentimiento",
      domain_ref: null,
      triggers: [],
      states: ["solicitado", "otorgado"],
      initial_state: "solicitado",
      owner: "subject:ana",
    };
    // guarda con `expected` = payload base (reversible, control optimista)
    const ok = vi.fn(async (url: string, init?: RequestInit) => {
      void url;
      void init;
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    });
    const client = createHttpClient("/sldb", ok);
    await client.save([
      {
        id: "MachineDoc:consentimiento",
        action: "update",
        model: "MachineDoc",
        payload: { ...base, title: "Consentimiento v2" },
        expected: base,
      },
    ]);
    const first = ok.mock.calls[0] || [];
    const init = (first.length > 1 ? (first[1] as { body?: string }) : {});
    const body = init.body || "";
    expect(body).toContain("\"expected\":");
    expect(body).toContain("MachineDoc:consentimiento");

    // un expected obsoleto (otro ya guardó) => 409 => SaveConflictError
    const stale = vi.fn(async () =>
      new Response(JSON.stringify({ ok: false, error: "conflicto de edición" }), { status: 409 }),
    );
    await expect(
      createHttpClient("/sldb", stale).save([
        {
          id: "MachineDoc:consentimiento",
          action: "update",
          model: "MachineDoc",
          payload: base,
          expected: { ...base, title: "Consentimiento OBSOLETO" },
        },
      ]),
    ).rejects.toBeInstanceOf(SaveConflictError);
  });
});
