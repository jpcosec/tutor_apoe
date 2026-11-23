import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import fixture from "../../core/__fixtures__/atoms.json";
import { SaveConflictError, SldbHttpError, type SldbClient } from "../../core/client";
import type { Edge, GraphDocument, SaveResult } from "../../core/contract";
import { SldbProvider } from "../../react/context";
import AtomosInformeView from "./AtomosInformeView";

const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));

const RENDERED = `---
resumen_modo: prosa
---

# Informe de prueba

## Resumen

- Hecho uno

## Decisiones

- Decisión uno
- Decisión dos

## Riesgos

## Pendientes

- Falta algo`;

const pubDoc = (version: number, informe = "inf1"): GraphDocument => ({
  id: `${informe}-v${version}`,
  model_name: "PublicacionDoc",
  path: `docs/${informe}-v${version}.md`,
  payload: { informe, version, title: "Informe de prueba", atoms: ["docs/atoms/a1.md"], resumen: "- x", decisiones: "", riesgos: "", pendientes: "" },
});

function mount(
  opts: {
    informeId?: string;
    saveImpl?: (ops: any[]) => Promise<SaveResult>;
    documentsFail?: boolean;
    published?: number[];
    createImpl?: (model: string, name: string, payload: any, docs: GraphDocument[]) => Promise<any>;
  } = {},
) {
  const docs = clone(fixture.documents) as unknown as GraphDocument[];
  const edges = clone(fixture.edges) as Edge[];
  let failing = !!opts.documentsFail;
  // El fixture guarda `kind:riesgo`; la sintaxis de la vista es `tipo:riesgo`.
  docs.find((d) => d.id === "inf1")!.payload.riesgos_query = "tipo:riesgo";
  for (const v of opts.published ?? []) docs.push(pubDoc(v));
  const createDocument = vi.fn(
    opts.createImpl ??
      (async (model: string, name: string, payload: any, all: GraphDocument[]) => {
        if (all.some((d) => d.id === name)) throw new SaveConflictError("ya existe", null);
        all.push({ id: name, model_name: model, path: `docs/${name}.md`, payload });
        return { ok: true, id: name, version: "h" };
      }),
  );
  const save = vi.fn(
    opts.saveImpl ??
      (async (ops: any[]) => {
        for (const op of ops) {
          const d = docs.find((x) => x.id === op.id)!;
          d.payload = clone(op.payload);
        }
        return { ok: true, saved: ops.map((o) => o.id) };
      }),
  );
  const client = {
    documents: vi.fn(async () => {
      if (failing) throw new Error("sin red");
      return clone(docs);
    }),
    getEdges: async () => clone(edges),
    document: async (id: string) => clone(docs.find((d) => d.id === id)!),
    render: vi.fn(async () => RENDERED),
    createDocument: (model: string, name: string, payload: any) => createDocument(model, name, payload, docs),
    save,
  } as unknown as SldbClient;
  render(
    <SldbProvider client={client}>
      <AtomosInformeView informeId={opts.informeId ?? "inf1"} />
    </SldbProvider>,
  );
  return { save, docs, client, createDocument, heal: () => (failing = false) };
}

/** Los cambios de un save: campo -> valor nuevo. */
const changed = (save: ReturnType<typeof vi.fn>, call: number, field: string) => (save.mock.calls[call]![0][0].payload as Record<string, unknown>)[field];

describe("AtomosInformeView", () => {
  it("muestra cargando y luego el esqueleto con contadores y gate", async () => {
    mount();
    expect(screen.getByText("Cargando informe…")).toBeInTheDocument();
    const nav = await screen.findByRole("navigation", { name: "Esqueleto" });
    expect(within(nav).getAllByRole("button")).toHaveLength(4);
    expect(within(nav).getByLabelText("1 incluidos en Resumen")).toHaveTextContent("1");
    expect(within(nav).getByLabelText("0 incluidos en Riesgos")).toHaveTextContent("0");
    expect(screen.getByText("Listo para publicar")).toBeInTheDocument();
    expect(screen.getByText("Las secciones las define el tipo de informe.")).toBeInTheDocument();
    expect(screen.getByText("Sin publicar")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publicar v1" })).toBeEnabled();
  });

  it("publica: crea la foto inmutable con el render real y pasa a Publicado como v2", async () => {
    const { createDocument, docs } = mount({ published: [1] });
    expect(await screen.findByText("Publicado como v1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Publicar v2" }));
    expect(await screen.findByText("Publicado como v2")).toBeInTheDocument();
    expect(createDocument).toHaveBeenCalledTimes(1);
    const [model, name, payload] = createDocument.mock.calls[0]!;
    expect(model).toBe("PublicacionDoc");
    expect(name).toBe("inf1-v2");
    expect(payload).toMatchObject({ informe: "inf1", version: 2, title: "Informe de prueba", resumen: "- Hecho uno", decisiones: "- Decisión uno\n- Decisión dos", riesgos: "", pendientes: "- Falta algo" });
    expect(payload.atoms).toEqual(["docs/atoms/a1.md", "docs/atoms/a2.md"]);
    expect(docs.some((d) => d.id === "inf1-v2")).toBe(true);
    expect(screen.getByRole("button", { name: "Publicar v3" })).toBeEnabled();
    const list = screen.getByLabelText("Versiones publicadas");
    expect(within(list).getByRole("link", { name: "v2" })).toHaveAttribute("href", "#/doc/inf1-v2");
    expect(within(list).getByRole("link", { name: "v1" })).toHaveAttribute("href", "#/doc/inf1-v1");
  });

  it("con átomos nuevos por revisar el botón queda deshabilitado con su razón", async () => {
    mount({ published: [1] });
    await screen.findByText("Publicado como v1");
    fireEvent.click(screen.getByRole("button", { name: /^Riesgos/ }));
    fireEvent.click(screen.getByRole("button", { name: "Actualizar" }));
    await screen.findByText(/1 átomo nuevo por revisar/);
    const btn = screen.getByRole("button", { name: "Publicar v2" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", "Revisa los átomos nuevos antes de republicar");
  });

  it("409 al publicar: relee las versiones y reintenta una vez", async () => {
    let calls = 0;
    const { createDocument, docs } = mount({
      published: [1],
      createImpl: async (model, name, payload, all) => {
        calls += 1;
        if (calls === 1) {
          // otro publicó v2 a la vez
          all.push(pubDoc(2));
          throw new SaveConflictError("ya existe", null);
        }
        all.push({ id: name, model_name: model, path: `docs/${name}.md`, payload });
        return { ok: true, id: name, version: "h" };
      },
    });
    await screen.findByText("Publicado como v1");
    fireEvent.click(screen.getByRole("button", { name: "Publicar v2" }));
    expect(await screen.findByText("Publicado como v3")).toBeInTheDocument();
    expect(createDocument.mock.calls.map((c) => c[1])).toEqual(["inf1-v2", "inf1-v3"]);
    expect(docs.filter((d) => d.model_name === "PublicacionDoc")).toHaveLength(3);
  });

  it("422 al publicar: muestra el error y conserva la vista", async () => {
    mount({
      published: [1],
      createImpl: async () => {
        throw new SldbHttpError("body inválido", 422, null);
      },
    });
    await screen.findByText("Publicado como v1");
    fireEvent.click(screen.getByRole("button", { name: /^Decisiones/ }));
    fireEvent.click(screen.getByRole("button", { name: "Publicar v2" }));
    expect(await screen.findByText("No se pudo publicar: body inválido")).toBeInTheDocument();
    expect(screen.getByText("Publicado como v1")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Slot Decisiones" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publicar v2" })).toBeEnabled();
  });

  it("informe inexistente", async () => {
    mount({ informeId: "nada" });
    expect(await screen.findByText("No existe el informe nada")).toBeInTheDocument();
  });

  it("error de red con reintentar", async () => {
    const { heal } = mount({ documentsFail: true });
    expect(await screen.findByText(/No se pudo leer el store: sin red/)).toBeInTheDocument();
    heal();
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("navigation", { name: "Esqueleto" })).toBeInTheDocument();
  });

  it("Actualizar produce nuevos, el gate cuenta, Aceptar los mueve a la lista y guarda el campo", async () => {
    const { save } = mount();
    await screen.findByRole("navigation", { name: "Esqueleto" });
    fireEvent.click(screen.getByRole("button", { name: /^Riesgos/ }));
    fireEvent.click(screen.getByRole("button", { name: "Actualizar" }));
    // riesgos_query = kind:riesgo (a4 y a6; a6 está excluido a mano) -> solo a4
    const nuevos = await screen.findByRole("list", { name: "Nuevos sin revisar" });
    expect(within(nuevos).getByText("Nuevo, sin revisar")).toBeInTheDocument();
    expect(screen.getByText("1 átomo nuevo por revisar")).toBeInTheDocument();
    expect(screen.getByLabelText("Tiene átomos nuevos")).toBeInTheDocument();

    fireEvent.click(within(nuevos).getByRole("button", { name: "Aceptar" }));
    await waitFor(() => expect(screen.queryByRole("list", { name: "Nuevos sin revisar" })).toBeNull());
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0]![0][0]).toMatchObject({ id: "inf1", action: "update", model: "InformeAvanceDoc" });
    expect(changed(save, 0, "riesgos")).toEqual(["docs/atoms/a4.md"]);
    expect(screen.getByText("Listo para publicar")).toBeInTheDocument();
    expect(await screen.findByText("Átomos del slot (1)")).toBeInTheDocument();
    expect(screen.getByText("Proveedor no soporta el volumen", { selector: "p" })).toBeInTheDocument();
  });

  it("Excluir un nuevo persiste solo `<slot>_excluidos`; Fijar persiste pins y lista", async () => {
    const { save } = mount();
    await screen.findByRole("navigation", { name: "Esqueleto" });
    fireEvent.click(screen.getByRole("button", { name: /^Riesgos/ }));
    fireEvent.click(screen.getByRole("button", { name: "Actualizar" }));
    const nuevos = await screen.findByRole("list", { name: "Nuevos sin revisar" });
    fireEvent.click(within(nuevos).getByRole("button", { name: "Excluir" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(changed(save, 0, "riesgos_excluidos")).toEqual(["docs/atoms/a6.md", "docs/atoms/a4.md"]);
    expect(changed(save, 0, "riesgos")).toEqual([]);

    // Decisiones: a2 ya está fijado -> Soltar pin persiste solo pins.
    fireEvent.click(screen.getByRole("button", { name: /^Decisiones/ }));
    expect(await screen.findByText("Fijado a mano")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Soltar pin" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    expect(changed(save, 1, "decisiones_pins")).toEqual([]);

    // Resumen: a1 "Por consulta" -> Fijar persiste pins.
    fireEvent.click(screen.getByRole("button", { name: /^Resumen/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Fijar" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(3));
    expect(changed(save, 2, "resumen_pins")).toEqual(["docs/atoms/a1.md"]);
  });

  it("un excluido se puede volver a incluir", async () => {
    const { save } = mount();
    await screen.findByRole("navigation", { name: "Esqueleto" });
    fireEvent.click(screen.getByRole("button", { name: /^Riesgos/ }));
    expect(await screen.findByText("Excluido a mano")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Volver a incluir" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(changed(save, 0, "riesgos_excluidos")).toEqual([]);
  });

  it("si el servidor rechaza, no cambia nada y muestra el error", async () => {
    const { save } = mount({ saveImpl: async () => ({ ok: false, error: "valor inválido" }) });
    await screen.findByRole("navigation", { name: "Esqueleto" });
    fireEvent.click(screen.getByRole("button", { name: /^Resumen/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Fijar" }));
    expect(await screen.findByText("valor inválido")).toBeInTheDocument();
    expect(save).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Fijar" })).toBeInTheDocument();
  });

  it("un conflicto de guardado ofrece recargar", async () => {
    mount({
      saveImpl: async () => {
        throw new SaveConflictError("cambió", {});
      },
    });
    await screen.findByRole("navigation", { name: "Esqueleto" });
    fireEvent.click(screen.getByRole("button", { name: /^Resumen/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Fijar" }));
    expect(await screen.findByText(/cambió en SLDB/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Recargar informe" }));
    await waitFor(() => expect(screen.queryByText(/cambió en SLDB/)).toBeNull());
  });

  it("la consulta se guarda al salir del campo y los chips reescriben el texto", async () => {
    const { save } = mount();
    await screen.findByRole("navigation", { name: "Esqueleto" });
    const input = screen.getByLabelText("Qué va en este slot");
    expect(input).toHaveValue("kind:hecho");
    fireEvent.change(input, { target: { value: "tipo:hecho tag:infra cola" } });
    fireEvent.blur(input);
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(changed(save, 0, "resumen_query")).toBe("tipo:hecho tag:infra cola");
    expect(await screen.findByText("Guardado")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Quitar filtro tag:infra" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    expect(changed(save, 1, "resumen_query")).toBe("tipo:hecho cola");
  });

  it("cambio de modo persiste y la vista previa cambia; la procedencia abre con el ancla", async () => {
    const { save } = mount();
    await screen.findByRole("navigation", { name: "Esqueleto" });
    // resumen ya está en prosa
    expect(screen.getByText("Vista previa unida, no redactada por un modelo.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Presentar como"), { target: { value: "tabla" } });
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(changed(save, 0, "resumen_modo")).toBe("tabla");
    await waitFor(() => expect(screen.queryByText("Vista previa unida, no redactada por un modelo.")).toBeNull());
    expect(screen.getAllByRole("table").length).toBe(1); // solo resumen; riesgos está en tabla pero vacío
    expect(screen.getAllByText(/documento guardado en disco renderiza siempre viñetas/).length).toBeGreaterThan(0);

    const doc = screen.getByRole("complementary", { name: "Documento final" });
    fireEvent.click(within(doc).getAllByRole("button", { name: "Reunión del 14/09" })[0]!);
    const dialog = screen.getByRole("dialog", { name: "Procedencia" });
    expect(within(dialog).getByText("Viene de 1 átomo")).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Abrir en el texto" })).toHaveAttribute("href", expect.stringMatching(/^#\/atomos\/texto\/acta\?atom=\w+$/));
    expect(within(doc).getAllByText("Este slot todavía no tiene átomos.").length).toBeGreaterThan(0);
  });

  it("avisa ancla rota cuando la cita ya no está en el acta", async () => {
    mount();
    await screen.findByRole("navigation", { name: "Esqueleto" });
    fireEvent.click(screen.getByRole("button", { name: /^Riesgos/ }));
    fireEvent.click(screen.getByRole("button", { name: "Actualizar" }));
    const nuevos = await screen.findByRole("list", { name: "Nuevos sin revisar" });
    fireEvent.click(within(nuevos).getByRole("button", { name: "Aceptar" }));
    // a4 cita "el proveedor no soporta la carga" y el acta dice "...el volumen"
    expect(await screen.findByText("ancla rota")).toBeInTheDocument();
  });
});
