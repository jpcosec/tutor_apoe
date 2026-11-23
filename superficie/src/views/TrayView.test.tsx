import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { SldbClient } from "../core/client";
import type { GraphDocument, RankHit, RankParams, SimilarityResult } from "../core/contract";
import { SldbProvider } from "../react/context";
import { TrayView } from "./TrayView";

const doc = (id: string, model: string, payload: Record<string, unknown>): GraphDocument =>
  ({ id, model_name: model, path: `docs/${id}.md`, version: "v", payload }) as GraphDocument;

/** Un modelo que declara `provenance`: sin ella el documento cae en la bandeja. */
const schema = {
  models: [{ id: "AtomDoc", model_ref: "m:AtomDoc", fields: [{ name: "provenance", kind: "string", required: false }] }],
  errors: [],
};

const DOCS = [
  doc("borrador-1", "AtomDoc", { title: "Cobranza sin fuente", body: "el cliente paga tarde", provenance: "" }),
  doc("ubicado-1", "AtomDoc", { title: "Cobranza mensual", body: "el cliente paga cada mes", provenance: "source/x.md" }),
  doc("ubicado-2", "AtomDoc", { title: "Otro", provenance: "source/y.md" }),
];

const hit = (name: string, score: number, title: string): RankHit =>
  ({ id: `AtomDoc:${name}`, model: "AtomDoc", name, score, payload: { title }, tags: [] }) as RankHit;

function mount(rank: (p: RankParams) => Promise<SimilarityResult<RankHit>>) {
  const spy = vi.fn(rank);
  const client = { documents: async () => DOCS, schema: async () => schema, rank: spy } as unknown as SldbClient;
  render(
    <SldbProvider client={client}>
      <TrayView />
    </SldbProvider>,
  );
  return spy;
}

describe("TrayView: sugerencia de destino", () => {
  it("ok con hits: muestra hasta 3 con puntaje y enlace, y consulta solo entre los ubicados", async () => {
    const rank = mount(async () => ({
      status: "ok",
      hits: [hit("ubicado-1", 0.62, "Cobranza mensual"), hit("ubicado-2", 0.5, "Otro"), hit("x", 0.4, "X"), hit("y", 0.37, "Y"), hit("bajo", 0.1, "Bajo")],
    }));
    const list = await screen.findByRole("list", { name: "Destinos sugeridos" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("62%");
    expect(within(items[0]!).getByRole("link", { name: "Cobranza mensual" })).toHaveAttribute("href", "#/doc/ubicado-1");
    expect(rank).toHaveBeenCalledTimes(1);
    const params = rank.mock.calls[0]![0];
    expect(params).toMatchObject({ k: 3, threshold: 0.35, among: ["AtomDoc:ubicado-1", "AtomDoc:ubicado-2"] });
    expect(params.refresh).toBeFalsy();
    expect(params.q).toContain("Cobranza sin fuente");
  });

  it("ok vacío: dice 'Sin parecidos', no un aviso de servicio", async () => {
    mount(async () => ({ status: "ok", hits: [] }));
    expect(await screen.findByText(/Sin parecidos/)).toBeInTheDocument();
    expect(screen.queryByText(/no disponible/i)).toBeNull();
    expect(screen.queryByRole("button", { name: "Indexar ahora" })).toBeNull();
  });

  it("not_indexed: avisa y 'Indexar ahora' pide con refresh:true y reintenta", async () => {
    let indexed = false;
    const rank = mount(async (p) => {
      if (p.refresh) {
        indexed = true;
        return { status: "ok", hits: [hit("ubicado-1", 0.7, "Cobranza mensual")] };
      }
      return indexed ? { status: "ok", hits: [hit("ubicado-1", 0.7, "Cobranza mensual")] } : { status: "not_indexed" };
    });
    expect(await screen.findByText(/todavía no está indexado/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Indexar ahora" }));
    expect(await screen.findByText("70%")).toBeInTheDocument();
    expect(rank.mock.calls.some(([p]) => p.refresh === true)).toBe(true);
    expect(screen.queryByRole("button", { name: "Indexar ahora" })).toBeNull();
  });

  it("indexar muestra cargando mientras espera", async () => {
    let release: (r: SimilarityResult<RankHit>) => void = () => {};
    mount((p) => (p.refresh ? new Promise((res) => (release = res)) : Promise.resolve({ status: "not_indexed" })));
    fireEvent.click(await screen.findByRole("button", { name: "Indexar ahora" }));
    expect(await screen.findByText(/Indexando el corpus/)).toBeInTheDocument();
    release({ status: "ok", hits: [] });
    expect(await screen.findByText(/Sin parecidos/)).toBeInTheDocument();
  });

  it("unavailable: 'Similitud no disponible: <razón>' y ningún ranking inventado", async () => {
    mount(async () => ({ status: "unavailable", reason: "ECONNREFUSED" }));
    expect(await screen.findByText("Similitud no disponible: ECONNREFUSED.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Destinos sugeridos" })).toBeNull();
    expect(screen.queryByText(/Sin parecidos/)).toBeNull();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Indexar ahora" })).toBeNull());
  });
});
