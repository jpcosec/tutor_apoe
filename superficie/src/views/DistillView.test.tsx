import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { SldbClient } from "../core/client";
import type { FieldRankHit, GraphDocument, RankParams, SchemaModel, SimilarityResult } from "../core/contract";
import { SldbProvider } from "../react/context";
import { DistillView } from "./DistillView";

const anchorModel: SchemaModel = {
  id: "AnchorDoc",
  model_ref: "pron.models:AnchorDoc",
  fields: [
    { name: "symbol", kind: "string", required: true },
    { name: "ref", kind: "string", required: true },
    { name: "motive", kind: "string", required: true },
  ],
};

const anchorDoc = (id: string, ref: string, motive: string): GraphDocument => ({
  id,
  model_name: "AnchorDoc",
  path: `${id}.yaml`,
  payload: { symbol: id, ref, motive },
});

const docs: GraphDocument[] = [
  anchorDoc("anchor-a", "(field Cliente telefono)", "el cliente deja un telefono de contacto"),
  anchorDoc("anchor-b", "(field Cliente region)", "la region define el precio del plan"),
  { id: "acta", model_name: "ActaDoc", path: "acta.yaml", payload: { body: "x" } },
];

const hit = (name: string, field: string, score: number): FieldRankHit => ({
  id: `docs/ActaDoc/${name}/${field}`,
  document_id: `ActaDoc:${name}`,
  field,
  model: "ActaDoc",
  name,
  score,
  text: "t",
  payload: {},
  tags: [],
});

type Rank = (p: RankParams) => SimilarityResult<FieldRankHit>;

function mount(rank: Rank) {
  const spy = vi.fn(async (p: RankParams) => rank(p));
  const client = {
    schema: async () => ({ models: [anchorModel], errors: [] }),
    documents: async () => docs,
    rank: spy,
  } as unknown as SldbClient;
  render(
    <SldbProvider client={client}>
      <DistillView />
    </SldbProvider>,
  );
  return { rank: spy };
}

const wait = { timeout: 3000 };
const ok = (...hits: FieldRankHit[]): SimilarityResult<FieldRankHit> => ({ status: "ok", hits });
const forPhone = (p: RankParams) => /telefono/.test(p.q);

let rank_built = false;

describe("DistillView · deduplicación de campos propuestos", () => {
  it("ok: marca duplicado y parecido con puntaje y enlace, y consulta campos sin sus propios anchors", async () => {
    const { rank } = mount((p) => (forPhone(p) ? ok(hit("acta", "contacto", 0.92), hit("acta", "body", 0.5)) : ok()));
    const dup = await screen.findByText("Posible duplicado de", {}, wait);
    const item = dup.closest("li") as HTMLElement;
    expect(within(item).getByRole("link", { name: "acta/contacto" })).toHaveAttribute("href", "#/doc/acta");
    expect(within(item).getByText("(92%)")).toBeInTheDocument();
    const similar = screen.getByText("Parecido a").closest("li") as HTMLElement;
    expect(within(similar).getByText("(50%)")).toBeInTheDocument();
    // El otro campo no tiene parecidos: es un resultado, dicho como tal.
    expect(screen.getByText("Sin campos parecidos")).toBeInTheDocument();

    expect(rank).toHaveBeenCalledTimes(2);
    for (const [params] of rank.mock.calls) {
      expect(params).toMatchObject({ fields: true, k: 2, threshold: 0.35, among: ["ActaDoc:acta"] });
      expect(params.refresh).toBeFalsy();
    }
  });

  it("ok vacío: Sin campos parecidos, y no es un aviso de estado", async () => {
    mount(() => ok());
    expect(await screen.findAllByText("Sin campos parecidos", {}, wait)).toHaveLength(2);
    expect(screen.queryByText(/no disponible/i)).toBeNull();
    expect(screen.queryByRole("button", { name: "Indexar ahora" })).toBeNull();
  });

  it("not_indexed: avisa y Indexar ahora consulta con refresh y reintenta", async () => {
    rank_built = false;
    const { rank } = mount((p) => (p.refresh || rank_built ? ((rank_built = true), ok(hit("acta", "contacto", 0.9))) : { status: "not_indexed" }));
    fireEvent.click(await screen.findByRole("button", { name: "Indexar ahora" }, wait));
    expect((await screen.findAllByText("Posible duplicado de", {}, wait)).length).toBeGreaterThan(0);
    expect(rank).toHaveBeenCalledWith(expect.objectContaining({ refresh: true }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Indexar ahora" })).toBeNull());
    expect(screen.queryByText("Sin campos parecidos")).toBeNull();
  });

  it("unavailable: dice no disponible con la razón y no muestra vacío", async () => {
    mount(() => ({ status: "unavailable", reason: "404" }));
    expect(await screen.findByText("Similitud no disponible: 404.", {}, wait)).toBeInTheDocument();
    expect(screen.queryByText("Sin campos parecidos")).toBeNull();
    expect(screen.queryByText(/Parecido a|Posible duplicado/)).toBeNull();
  });
});


