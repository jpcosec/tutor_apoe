import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { SldbClient } from "../core/client";
import { SldbHttpError } from "../core/client";
import type { FieldRankHit, SchemaModel, SimilarityResult } from "../core/contract";
import { SldbProvider } from "../react/context";
import { ReaderView } from "./ReaderView";

/** El contrato real del store: `pron.models:AnchorDoc`. */
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

const TEXT = "el cliente manifiesta que no será\nposible una conexión directa a SAP.";

const hit = (name: string, score: number, field = "quote"): FieldRankHit => ({
  id: `docs/M/${name}/${field}`, document_id: `docs/M/${name}`, field, model: "M", name, score, text: "", payload: {}, tags: [],
});
const ok = (...hits: FieldRankHit[]): SimilarityResult<FieldRankHit> => ({ status: "ok", hits });

function mount(rankImpl: (p: { refresh?: boolean }) => SimilarityResult<FieldRankHit> = () => ok()) {
  const save = vi.fn(async () => ({ ok: true, saved: ["anchor-no-sera-posible-una"] }));
  const rank = vi.fn(async (p: { refresh?: boolean }) => rankImpl(p));
  const client = { schema: async () => ({ models: [anchorDoc], errors: [] }), save, rank } as unknown as SldbClient;
  render(
    <SldbProvider client={client}>
      <ReaderView />
    </SldbProvider>,
  );
  return { save, rank };
}

/** Pega texto y selecciona un tramo, como lo haría el usuario en el textarea. */
function selectRange(textarea: HTMLTextAreaElement, start: number, end: number) {
  fireEvent.change(textarea, { target: { value: TEXT } });
  textarea.setSelectionRange(start, end);
  fireEvent.select(textarea);
  return textarea;
}

describe("ReaderView", () => {
  it("arma el formulario desde el schema y solo muestra campos declarados", async () => {
    mount();
    const textarea = (await screen.findByLabelText("Texto crudo")) as HTMLTextAreaElement;
    selectRange(textarea, 0, 2);
    expect(await screen.findByText(/línea 1/)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /^symbol/ })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /^ref/ })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /^motive/ })).toBeInTheDocument();
    // `provenance` no lo declara este modelo: no hay campo para él.
    expect(screen.queryByRole("textbox", { name: /provenance/ })).toBeNull();
  });

  const wait = { timeout: 3000 };
  const pick = async () => {
    const textarea = (await screen.findByLabelText("Texto crudo")) as HTMLTextAreaElement;
    selectRange(textarea, 0, 40);
  };

  it("ok con hits: muestra parecidos con puntaje y destaca el duplicado", async () => {
    const { rank } = mount(() => ok(hit("anchor-casi-igual", 0.91), hit("anchor-algo", 0.5)));
    await pick();
    const dup = await screen.findByText("Posible duplicado (91%)", {}, wait);
    expect(dup).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "anchor-casi-igual/quote" })).toHaveAttribute("href", "#/doc/anchor-casi-igual");
    expect(screen.getByRole("link", { name: "anchor-algo/quote" })).toHaveAttribute("href", "#/doc/anchor-algo");
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(rank).toHaveBeenCalledTimes(1);
    expect(rank).toHaveBeenCalledWith(expect.objectContaining({ k: 3, threshold: 0.35, fields: true, refresh: false }));
  });

  it("ok vacío: dice que es nuevo", async () => {
    mount(() => ok());
    await pick();
    expect(await screen.findByText("No hay nada parecido: es nuevo.", {}, wait)).toBeInTheDocument();
  });

  it("not_indexed: avisa y Indexar ahora reintenta con refresh", async () => {
    const { rank } = mount((p) => (p.refresh ? ok(hit("anchor-x", 0.6)) : { status: "not_indexed" }));
    await pick();
    fireEvent.click(await screen.findByRole("button", { name: "Indexar ahora" }, wait));
    expect(await screen.findByRole("link", { name: "anchor-x/quote" }, wait)).toBeInTheDocument();
    expect(rank).toHaveBeenLastCalledWith(expect.objectContaining({ refresh: true, fields: true }));
    expect(screen.queryByText("No hay nada parecido: es nuevo.")).toBeNull();
  });

  it("unavailable: dice no disponible con la razón, sin mostrarlo como vacío", async () => {
    mount(() => ({ status: "unavailable", reason: "404" }));
    await pick();
    expect(await screen.findByText("Similitud no disponible: 404.", {}, wait)).toBeInTheDocument();
    expect(screen.queryByText(/es nuevo/)).toBeNull();
  });

  it("no consulta con una selección demasiado corta", async () => {
    const { rank } = mount();
    const textarea = (await screen.findByLabelText("Texto crudo")) as HTMLTextAreaElement;
    selectRange(textarea, 0, 3);
    expect(await screen.findByText(/tramo más largo/)).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 600));
    expect(rank).not.toHaveBeenCalled();
  });

  it("crear el anchor sigue funcionando con el aviso de duplicado presente", async () => {
    const { save } = mount(() => ok(hit("anchor-casi-igual", 0.95)));
    await pick();
    await screen.findByText("Posible duplicado (95%)", {}, wait);
    fireEvent.change(screen.getByRole("textbox", { name: /^ref/ }), { target: { value: "(model X)" } });
    fireEvent.change(screen.getByRole("textbox", { name: /^motive/ }), { target: { value: "porque sí" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar anchor" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
  });

  it("guarda con POST /save y enlaza al documento creado", async () => {
    const { save } = mount();
    const textarea = (await screen.findByLabelText("Texto crudo")) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: TEXT } });
    textarea.setSelectionRange(3, 46);
    fireEvent.select(textarea);

    fireEvent.change(screen.getByRole("textbox", { name: /^ref/ }), { target: { value: "(model DomainAtom)" } });
    fireEvent.change(screen.getByRole("textbox", { name: /^motive/ }), { target: { value: "el cliente no quiere conexión directa" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar anchor" }));

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenCalledWith([
      {
        id: "anchor-cliente-manifiesta-que-no",
        action: "create",
        model: "AnchorDoc",
        payload: {
          symbol: "cliente-manifiesta-que-no",
          ref: "(model DomainAtom)",
          motive: "el cliente no quiere conexión directa",
        },
      },
    ]);
    const link = await screen.findByRole("link", { name: "Abrir documento" });
    expect(link).toHaveAttribute("href", "#/doc/anchor-cliente-manifiesta-que-no");
    // El tramo anclado queda marcado en el texto.
    expect(document.querySelectorAll("mark.reader-mark").length).toBe(1);
  });

  it("muestra el mensaje del backend tal cual", async () => {
    const client = {
      schema: async () => ({ models: [anchorDoc], errors: [] }),
      save: async () => {
        throw new SldbHttpError("AnchorDoc: ref inválido.", 422, { error: "AnchorDoc: ref inválido." });
      },
    } as unknown as SldbClient;
    render(
      <SldbProvider client={client}>
        <ReaderView />
      </SldbProvider>,
    );
    const textarea = (await screen.findByLabelText("Texto crudo")) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: TEXT } });
    textarea.setSelectionRange(0, 10);
    fireEvent.select(textarea);
    fireEvent.change(screen.getByRole("textbox", { name: /^ref/ }), { target: { value: "x" } });
    fireEvent.change(screen.getByRole("textbox", { name: /^motive/ }), { target: { value: "y" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar anchor" }));
    expect(await screen.findByText("AnchorDoc: ref inválido.")).toBeInTheDocument();
  });
});
