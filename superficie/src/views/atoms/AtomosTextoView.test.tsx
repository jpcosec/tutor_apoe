import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import fixture from "../../core/__fixtures__/atoms.json";
import { SaveConflictError, SldbHttpError, type SldbClient } from "../../core/client";
import type { GraphDocument, Payload } from "../../core/contract";
import { SldbProvider } from "../../react/context";
import AtomosTextoView from "./AtomosTextoView";

const DOCS = fixture.documents as unknown as GraphDocument[];
const payloadOf = (id: string) => DOCS.find((d) => d.id === id)!.payload;
const ACTA_BODY = payloadOf("acta").body as string;

function mount(overrides: Partial<SldbClient> = {}, docs: GraphDocument[] = DOCS) {
  const save = vi.fn(async (_changes: unknown[]) => ({ ok: true, saved: [] as string[] }));
  const createDocument = vi.fn(async (_m: string, name: string) => ({ ok: true, id: name, version: "v" }));
  const client = {
    documents: async () => docs,
    getEdges: async () => [],
    document: async (id: string) => {
      const d = docs.find((x) => x.id === id)!;
      return { id: d.id, model_name: d.model_name, path: d.path, payload: d.payload };
    },
    save,
    createDocument,
    ...overrides,
  } as unknown as SldbClient;
  render(
    <SldbProvider client={client}>
      <AtomosTextoView actaId="acta" />
    </SldbProvider>,
  );
  return { save, createDocument };
}

const region = () => screen.getByRole("region", { name: /Texto fuente/ });
const mark = (id: string) => region().querySelector(`[data-atom-mark="${id}"]`) as HTMLElement | null;
const card = (id: string) => document.querySelector(`[data-atom-card="${id}"]`) as HTMLElement;

describe("AtomosTextoView · subrayados", () => {
  it("cuenta átomos, pinta los tres estados de ancla y aparta los descartados", async () => {
    mount();
    expect(await screen.findByText("5 átomos, 3 sin confirmar")).toBeInTheDocument();

    // intacto + confirmado
    expect(mark("a1")).toHaveTextContent("Reunión del 14/09");
    expect(mark("a1")).toHaveAttribute("data-anchor", "intact");
    expect(mark("a1")).toHaveAttribute("data-status", "confirmado");
    expect(mark("a1")!.className).toContain("is-confirmed");
    // intacto + propuesto → punteado
    expect(mark("a5")).toHaveTextContent("definir el esquema de eventos");
    expect(mark("a5")!.className).toContain("is-proposed");
    // movido: se subraya donde está la cita ahora, no en [89,125)
    expect(mark("a3")).toHaveAttribute("data-anchor", "drifted");
    expect(mark("a3")).toHaveTextContent("Tomás será responsable de la ingesta");
    expect(mark("a3")!.className).toContain("is-moved");
    expect(within(card("a3")).getByRole("button", { name: "Reparar ancla" })).toBeInTheDocument();
    // huérfano: sin subrayado, con aviso en su tarjeta
    expect(mark("a4")).toBeNull();
    expect(within(card("a4")).getByText(/El texto cambió/)).toBeInTheDocument();
    // descartado: no está en el texto ni en el panel principal, sí dentro de <details>
    expect(mark("a6")).toBeNull();
    const details = screen.getByText("Descartados (1)").closest("details")!;
    expect(details).toContainElement(card("a6"));
    expect(within(card("a6")).getByRole("button", { name: "Restaurar" })).toBeInTheDocument();
    // el texto fuente se lee completo y es de solo lectura
    expect(region().textContent).toBe(ACTA_BODY);
    expect(region().querySelector("input, textarea, [contenteditable]")).toBeNull();
  });

  it("el filtro por tipo usa aria-pressed y oculta los demás átomos", async () => {
    mount();
    await screen.findByText("5 átomos, 3 sin confirmar");
    const riesgo = screen.getByRole("button", { name: /Riesgo/ });
    expect(riesgo).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(riesgo);
    expect(riesgo).toHaveAttribute("aria-pressed", "true");
    expect(card("a4")).toBeTruthy();
    expect(card("a1")).toBeNull();
    expect(mark("a1")).toBeNull();
  });

  it("hover y click enfocan el átomo y su tarjeta; los demás se atenúan", async () => {
    mount();
    await screen.findByText("5 átomos, 3 sin confirmar");
    fireEvent.click(mark("a2")!);
    expect(card("a2")).toHaveAttribute("aria-current", "true");
    expect(card("a2").className).toContain("is-active");
    expect(card("a1").className).toContain("is-dim");
    expect(mark("a1")!.className).toContain("is-dim");
    // Enter en una tarjeta la enfoca
    fireEvent.keyDown(card("a5"), { key: "Enter" });
    expect(card("a5")).toHaveAttribute("aria-current", "true");
    expect(mark("a5")!.className).toContain("is-active");
  });

  it("'Baja confianza primero' reordena las tarjetas", async () => {
    const docs = DOCS.map((d) => (d.id === "a5" ? { ...d, payload: { ...d.payload, conf: 0.1 } } : d));
    mount({}, docs);
    await screen.findByText("5 átomos, 3 sin confirmar");
    const order = () => [...document.querySelectorAll("[data-atom-card]")].map((n) => n.getAttribute("data-atom-card"));
    expect(order().slice(0, 5)).toEqual(["a1", "a2", "a3", "a4", "a5"]);
    fireEvent.click(screen.getByLabelText("Baja confianza primero"));
    expect(order()[0]).toBe("a5");
  });

  it("'Re-extraer' está deshabilitado y dice por qué", async () => {
    mount();
    const button = await screen.findByRole("button", { name: /Re-extraer/ });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "Falta el extractor: aún no existe endpoint");
  });
});

describe("AtomosTextoView · acciones", () => {
  it("Confirmar escribe status=confirmado con expected", async () => {
    const { save } = mount();
    await screen.findByText("5 átomos, 3 sin confirmar");
    fireEvent.click(within(card("a3")).getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenCalledWith([
      { id: "a3", action: "update", model: "AtomDoc", payload: { ...payloadOf("a3"), status: "confirmado" }, expected: payloadOf("a3") },
    ]);
  });

  it("Descartar escribe status=descartado (no borra) y Restaurar lo devuelve a propuesto", async () => {
    const { save } = mount();
    await screen.findByText("5 átomos, 3 sin confirmar");
    fireEvent.click(within(card("a5")).getByRole("button", { name: "Descartar" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenLastCalledWith([
      { id: "a5", action: "update", model: "AtomDoc", payload: { ...payloadOf("a5"), status: "descartado" }, expected: payloadOf("a5") },
    ]);
    fireEvent.click(within(card("a6")).getByRole("button", { name: "Restaurar" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    expect((save.mock.calls[1]![0] as Array<{ payload: Payload; action: string }>)[0]).toMatchObject({ action: "update", payload: { status: "propuesto" } });
  });

  it("Reparar ancla escribe start y end nuevos", async () => {
    const { save } = mount();
    await screen.findByText("5 átomos, 3 sin confirmar");
    fireEvent.click(within(card("a3")).getByRole("button", { name: "Reparar ancla" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    const start = ACTA_BODY.indexOf("Tomás será responsable de la ingesta");
    const calls = save.mock.calls as unknown as Array<[Array<{ payload: Payload }>]>;
    expect(calls[0]![0][0]!.payload).toMatchObject({ start });
    // el store real relee el documento entre escrituras; el mock es estático, así que solo se verifica la 2ª por su campo
    expect(calls[1]![0][0]!.payload).toMatchObject({ end: start + "Tomás será responsable de la ingesta".length });
  });

  it("cambia el tipo y edita el texto en el lugar", async () => {
    const { save } = mount();
    await screen.findByText("5 átomos, 3 sin confirmar");
    fireEvent.change(within(card("a5")).getByLabelText("Tipo del átomo a5"), { target: { value: "decision" } });
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save.mock.calls[0]![0]).toMatchObject([{ id: "a5", payload: { kind: "decision" } }]);

    fireEvent.click(within(card("a5")).getByRole("button", { name: "Editar texto" }));
    const input = screen.getByLabelText("Texto del átomo a5");
    fireEvent.change(input, { target: { value: "Definir el esquema" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    expect(save.mock.calls[1]![0]).toMatchObject([{ id: "a5", payload: { text: "Definir el esquema" } }]);
  });

  it("muestra el error por tarjeta y ofrece recargar en conflicto", async () => {
    const save = vi.fn().mockRejectedValueOnce(new SldbHttpError("boom", 500, null)).mockRejectedValueOnce(new SaveConflictError("cambió", null));
    mount({ save } as Partial<SldbClient>);
    await screen.findByText("5 átomos, 3 sin confirmar");
    fireEvent.click(within(card("a3")).getByRole("button", { name: "Confirmar" }));
    expect(await within(card("a3")).findByText(/No se guardó: boom/)).toBeInTheDocument();
    expect(within(card("a1")).queryByRole("alert")).toBeNull();
    fireEvent.click(within(card("a3")).getByRole("button", { name: "Confirmar" }));
    expect(await within(card("a3")).findByRole("button", { name: "Recargar" })).toBeInTheDocument();
  });

  it("'Ver en el grafo' navega a #/atomos/grafo", async () => {
    mount();
    await screen.findByText("5 átomos, 3 sin confirmar");
    fireEvent.click(within(card("a1")).getByRole("button", { name: "Ver en el grafo" }));
    expect(window.location.hash).toBe("#/atomos/grafo?atom=a1"); // lleva el átomo enfocado
  });
});

function selectText(node: Node, from: number, endNode: Node = node, to: number = from) {
  const range = document.createRange();
  range.setStart(node, from);
  range.setEnd(endNode, to);
  const sel = window.getSelection()!;
  sel.removeAllRanges();
  sel.addRange(range);
  fireEvent.mouseUp(region());
}

describe("AtomosTextoView · crear desde la selección", () => {
  it("calcula offsets globales y llama a createAtom con el payload de la selección", async () => {
    const { createDocument } = mount();
    await screen.findByText("5 átomos, 3 sin confirmar");
    const gap = ACTA_BODY.indexOf("Riesgo");
    const seg = region().querySelector(`[data-start="118"]`)!; // tramo sin átomo entre a3 (movido) y a5
    const text = seg.firstChild!;
    selectText(text, gap - 118, text, gap - 118 + "Riesgo".length);
    fireEvent.click(await screen.findByRole("button", { name: "Crear átomo desde la selección" }));
    await waitFor(() => expect(createDocument).toHaveBeenCalledTimes(1));
    expect(createDocument).toHaveBeenCalledWith("AtomDoc", "a7", {
      kind: "hecho",
      status: "propuesto",
      source: "ActaDoc:acta",
      source_field: "body",
      start: gap,
      end: gap + 6,
      tags: [],
      text: "Riesgo",
      quote: "Riesgo",
      conf: 1,
    });
  });

  it("rechaza selecciones que cruzan párrafos con un mensaje claro", async () => {
    const docs = DOCS.filter((d) => d.model_name !== "AtomDoc").map((d) =>
      d.id === "acta" ? { ...d, payload: { ...d.payload, body: "Uno dos.\n\nTres cuatro." } } : d,
    );
    const { createDocument } = mount({}, docs);
    await screen.findByText("0 átomos, 0 sin confirmar");
    const [p1, p2] = [...region().querySelectorAll("p")];
    selectText(p1!.firstChild!.firstChild!, 4, p2!.firstChild!.firstChild!, 4);
    expect(await screen.findByText(/cruza un límite de párrafo/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Crear átomo desde la selección" })).toBeNull();
    expect(createDocument).not.toHaveBeenCalled();
  });

  it("no ofrece crear con una selección colapsada", async () => {
    mount();
    await screen.findByText("5 átomos, 3 sin confirmar");
    const text = region().querySelector("p")!.firstChild!.firstChild!.firstChild!;
    selectText(text, 3, text, 3);
    expect(screen.queryByRole("button", { name: "Crear átomo desde la selección" })).toBeNull();
  });
});

describe("AtomosTextoView · estados", () => {
  it("cargando", () => {
    mount({ documents: () => new Promise<GraphDocument[]>(() => undefined) });
    expect(screen.getByRole("status")).toHaveTextContent("Cargando átomos…");
  });

  it("error de carga, con reintento", async () => {
    mount({ documents: async () => { throw new SldbHttpError("SLDB caído", 503, null); } });
    expect(await screen.findByRole("alert")).toHaveTextContent("SLDB caído");
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });

  it("acta inexistente", async () => {
    mount({}, DOCS.filter((d) => d.model_name !== "ActaDoc"));
    expect(await screen.findByText(/No existe el acta/)).toBeInTheDocument();
  });
});
