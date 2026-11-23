import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { SldbClient } from "../../core/client";
import type { Edge, GraphDocument } from "../../core/contract";
import fixture from "../../core/__fixtures__/atoms.json";
import { SldbProvider } from "../../react/context";
import AtomosGrafoView from "./AtomosGrafoView";

const docs = fixture.documents as unknown as GraphDocument[];
const edges = fixture.edges as Edge[];

function mount(opts: { documents?: () => Promise<GraphDocument[]>; getEdges?: () => Promise<Edge[]>; createDocument?: ReturnType<typeof vi.fn> } = {}) {
  const createDocument = opts.createDocument ?? vi.fn(async () => ({ ok: true, id: "rel-1", version: "v" }));
  const client = {
    documents: opts.documents ?? (async () => docs),
    getEdges: opts.getEdges ?? (async () => edges),
    createDocument,
  } as unknown as SldbClient;
  render(
    <SldbProvider client={client}>
      <AtomosGrafoView />
    </SldbProvider>,
  );
  return { createDocument };
}

const node = (id: string) => document.querySelector(`[data-node-key="AtomDoc:${id}"]`) as SVGGElement;

/** Arrastra del átomo `from` al átomo `to` con pointer events. */
function connect(from: string, to: string) {
  fireEvent.pointerDown(node(from), { clientX: 10, clientY: 10, button: 0 });
  fireEvent.pointerMove(screen.getByRole("group", { name: "Grafo de átomos" }), { clientX: 60, clientY: 60 });
  fireEvent.pointerUp(node(to), { clientX: 80, clientY: 80 });
}

beforeEach(() => {
  window.location.hash = "";
});

describe("AtomosGrafoView", () => {
  it("muestra cargando y luego nodos (sin descartados) y aristas", async () => {
    mount();
    expect(screen.getByText(/Leyendo el grafo/)).toBeInTheDocument();
    await screen.findByRole("group", { name: "Grafo de átomos" });
    for (const id of ["a1", "a2", "a3", "a4", "a5"]) expect(node(id)).toBeTruthy();
    expect(node("a6")).toBeNull(); // descartado
    expect(screen.getByText(/5 átomos · 1 relación/)).toBeInTheDocument();
    // 1 directa + 2 heredadas del grupo infra; la referencia hacia el acta no se dibuja
    const aristas = screen.getAllByRole("button", { name: /^Relación motiva/ });
    expect(aristas).toHaveLength(3);
    expect(aristas.filter((a) => /heredada/.test(a.getAttribute("aria-label")!))).toHaveLength(2);
    expect(screen.getByRole("button", { name: /Decisión: Reemplazar el lote por una cola.*arquitectura/ })).toBeInTheDocument();
  });

  it("estado vacío", async () => {
    mount({ documents: async () => [], getEdges: async () => [] });
    expect(await screen.findByText("Sin átomos todavía")).toBeInTheDocument();
  });

  it("error de red con reintentar", async () => {
    let fail = true;
    mount({
      documents: async () => {
        if (fail) throw new Error("sin red");
        return docs;
      },
    });
    expect(await screen.findByText(/No se pudo leer el grafo: sin red/)).toBeInTheDocument();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    await screen.findByRole("group", { name: "Grafo de átomos" });
    expect(node("a2")).toBeTruthy();
  });

  it("plegar un grupo deja un solo nodo y fusiona; desplegar lo restaura", async () => {
    mount();
    await screen.findByRole("group", { name: "Grafo de átomos" });
    fireEvent.click(screen.getByRole("button", { name: "Plegar grupo infra" }));
    expect(node("a2")).toBeNull();
    expect(document.querySelector('[data-node-key="group:infra"]')).toBeTruthy();
    expect(screen.queryAllByRole("button", { name: /^Relación motiva/ })).toHaveLength(0); // todas internas a infra
    fireEvent.click(screen.getByRole("button", { name: "Desplegar grupo infra" }));
    expect(node("a2")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /^Relación motiva/ })).toHaveLength(3);
  });

  it("clic en un grupo de la barra resalta sus átomos", async () => {
    mount();
    await screen.findByRole("group", { name: "Grafo de átomos" });
    const side = screen.getByRole("complementary", { name: "Grupos" });
    fireEvent.click(within(side).getByRole("button", { name: "reuniones" }));
    expect(node("a1")).not.toHaveClass("is-dim");
    expect(node("a2")).toHaveClass("is-dim");
    fireEvent.click(within(side).getByRole("button", { name: "reuniones" }));
    expect(node("a2")).not.toHaveClass("is-dim");
  });

  it("filtrar un tipo oculta sus aristas", async () => {
    mount();
    await screen.findByRole("group", { name: "Grafo de átomos" });
    fireEvent.click(screen.getByRole("button", { name: "motiva", pressed: true }));
    expect(screen.queryAllByRole("button", { name: /^Relación motiva/ })).toHaveLength(0);
  });

  it("inspector de átomo: relaciones, ancla, dirección y Ver en el texto; Escape cierra", async () => {
    mount();
    await screen.findByRole("group", { name: "Grafo de átomos" });
    fireEvent.keyDown(node("a2"), { key: "Enter" });
    const insp = screen.getByRole("complementary", { name: "Inspector" });
    expect(within(insp).getByText("AtomDoc:a2")).toBeInTheDocument();
    expect(within(insp).getAllByLabelText("entrante")).toHaveLength(3); // a5 directa + a3, a4 heredadas de infra
    expect(within(insp).queryAllByLabelText("saliente")).toHaveLength(0);
    expect(within(insp).getByTestId("anchor-state")).toHaveTextContent(/intacta|movida|huérfana/);
    fireEvent.click(within(insp).getByRole("button", { name: "Ver en el texto" }));
    expect(window.location.hash).toBe("#/atomos/texto/acta?atom=a2"); // lleva el átomo enfocado
    fireEvent.keyDown(node("a2"), { key: "Escape" });
    expect(screen.queryByRole("complementary", { name: "Inspector" })).toBeNull();
  });

  it("inspector de arista: origen, destino, tipo y RelationDoc", async () => {
    mount();
    await screen.findByRole("group", { name: "Grafo de átomos" });
    const direct = screen.getAllByRole("button", { name: /^Relación motiva:/ }).find((e) => !/heredada/.test(e.getAttribute("aria-label")!))!;
    fireEvent.click(direct);
    const insp = screen.getByRole("complementary", { name: "Inspector" });
    expect(within(insp).getByText("r1")).toBeInTheDocument();
    expect(within(insp).getByText("Relación explícita.")).toBeInTheDocument();
  });

  it("arrastrar de un átomo a otro abre el menú con los tipos válidos y crea el RelationDoc", async () => {
    const { createDocument } = mount();
    await screen.findByRole("group", { name: "Grafo de átomos" });
    connect("a1", "a3");
    const menu = screen.getByRole("menu", { name: "Tipo de relación" });
    // `cubre` no admite átomos como origen: solo `motiva`
    expect(within(menu).getAllByRole("menuitem").map((b) => b.textContent)).toEqual([expect.stringContaining("motiva")]);
    fireEvent.click(within(menu).getByRole("menuitem"));
    await waitFor(() => expect(createDocument).toHaveBeenCalledTimes(1));
    expect(createDocument).toHaveBeenCalledWith("RelationDoc", "rel-1", {
      title: expect.stringContaining("motiva"),
      source_id: "AtomDoc:a1",
      target_id: "AtomDoc:a3",
      relation_type: "motiva",
      condition: "",
      notes: "",
    });
    expect(await screen.findByText(/Relación rel-1 creada/)).toBeInTheDocument();
  });

  it("si la relación ya existe no hay tipos válidos: mensaje claro y no crea", async () => {
    const { createDocument } = mount();
    await screen.findByRole("group", { name: "Grafo de átomos" });
    connect("a5", "a2"); // ya existe a5 motiva a2
    expect(screen.getByRole("alert")).toHaveTextContent(/No hay tipos de relación válidos/);
    expect(screen.queryByRole("menuitem")).toBeNull();
    expect(createDocument).not.toHaveBeenCalled();
  });

  it("soltar fuera de un átomo no hace nada; soltar sobre sí mismo tampoco", async () => {
    mount();
    await screen.findByRole("group", { name: "Grafo de átomos" });
    connect("a1", "a1");
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("un error 409 del servidor se muestra y conserva la vista", async () => {
    const createDocument = vi.fn(async () => {
      throw new Error("409 documento ya existe");
    });
    mount({ createDocument });
    await screen.findByRole("group", { name: "Grafo de átomos" });
    fireEvent.click(screen.getByRole("button", { name: "Plegar grupo reuniones" }));
    fireEvent.click(screen.getByRole("button", { name: "Desplegar grupo reuniones" }));
    connect("a1", "a3");
    fireEvent.click(screen.getByRole("menuitem"));
    expect(await screen.findByText(/No se creó la relación: 409 documento ya existe/)).toBeInTheDocument();
    expect(node("a1")).toBeTruthy();
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("el nombre rel-<n> toma el siguiente libre", async () => {
    const withRel = [...docs, { id: "rel-4", model_name: "RelationDoc", path: "docs/rel-4.md", payload: {}, semantic_tags: [] } as unknown as GraphDocument];
    const { createDocument } = mount({ documents: async () => withRel });
    await screen.findByRole("group", { name: "Grafo de átomos" });
    connect("a1", "a3");
    fireEvent.click(screen.getByRole("menuitem"));
    await waitFor(() => expect(createDocument).toHaveBeenCalled());
    expect(createDocument.mock.calls[0]![1]).toBe("rel-5");
  });

  describe("relaciones sobre un grupo (GrupoDoc)", () => {
    const rt = (id: string, source_types: string[], target_types: string[]) =>
      ({ id, model_name: "RelationTypeDoc", path: `docs/rt/${id}.md`, payload: { name: id, source_types, target_types, cardinality: "many_to_many", description: `d ${id}` }, semantic_tags: [] }) as unknown as GraphDocument;
    const grupoTypes = [rt("condiciona", ["AtomDoc", "GrupoDoc"], ["AtomDoc", "GrupoDoc"]), rt("responsable_de", ["AtomDoc", "GrupoDoc"], ["AtomDoc"])];
    const withTypes = [...docs, ...grupoTypes];
    const head = (g: string) => document.querySelector(`[data-group-head="${g}"]`) as SVGGElement;
    const dropOnHead = (from: string, g: string) => {
      fireEvent.pointerDown(node(from), { clientX: 10, clientY: 10, button: 0 });
      fireEvent.pointerMove(screen.getByRole("group", { name: "Grafo de átomos" }), { clientX: 60, clientY: 60 });
      expect(head(g).getAttribute("class")).toContain("is-droppable");
      fireEvent.pointerUp(head(g), { clientX: 80, clientY: 80 });
    };

    it("una relación cuyo extremo es GrupoDoc se dibuja punteada hacia cada átomo del grupo y el inspector dice de dónde viene", async () => {
      const groupEdge: Edge = { id: "e9", source: "GrupoDoc:infra-ingesta", target: "AtomDoc:a1", type: "condiciona", origin: "relation_doc", relationDoc: "r10" };
      mount({ documents: async () => withTypes, getEdges: async () => [...edges, groupEdge] });
      await screen.findByRole("group", { name: "Grafo de átomos" });
      const heredadas = screen.getAllByRole("button", { name: /^Relación condiciona heredada/ });
      expect(heredadas.length).toBeGreaterThan(0);
      expect(heredadas.every((h) => h.classList.contains("is-inherited"))).toBe(true);
      fireEvent.click(heredadas[0]!);
      const insp = screen.getByRole("complementary", { name: "Inspector" });
      expect(within(insp).getByText("r10")).toBeInTheDocument();
      expect(within(insp).getByText(/Heredada del grupo infra\.ingesta por la relación r10 \(GrupoDoc:infra-ingesta → AtomDoc:a1\)/)).toBeInTheDocument();
    });

    it("soltar un átomo sobre el encabezado de un grupo ofrece solo los tipos que admiten GrupoDoc y crea el GrupoDoc y luego el RelationDoc", async () => {
      const { createDocument } = mount({ documents: async () => withTypes });
      await screen.findByRole("group", { name: "Grafo de átomos" });
      dropOnHead("a1", "reuniones");
      const menu = screen.getByRole("menu", { name: "Tipo de relación" });
      expect(within(menu).getAllByRole("menuitem").map((b) => b.querySelector("strong")!.textContent)).toEqual(["condiciona"]);
      expect(within(menu).getByText(/la relación la heredan todos sus átomos/)).toBeInTheDocument();
      fireEvent.click(within(menu).getByRole("menuitem"));
      await waitFor(() => expect(createDocument).toHaveBeenCalledTimes(2));
      expect(createDocument.mock.calls[0]).toEqual(["GrupoDoc", "reuniones", { title: "reuniones", tag: "reuniones", description: "" }]);
      expect(createDocument.mock.calls[1]![0]).toBe("RelationDoc");
      expect(createDocument.mock.calls[1]![2]).toMatchObject({ source_id: "AtomDoc:a1", target_id: "GrupoDoc:reuniones", relation_type: "condiciona" });
      expect(await screen.findByText(/Relación rel-1 creada/)).toBeInTheDocument();
    });

    it("desde el encabezado de un grupo hacia un átomo: el grupo es el origen; si el GrupoDoc ya existe no se vuelve a crear", async () => {
      const g = { id: "infra", model_name: "GrupoDoc", path: "docs/grupos/infra.md", payload: { tag: "infra" }, semantic_tags: [] } as unknown as GraphDocument;
      const { createDocument } = mount({ documents: async () => [...withTypes, g] });
      await screen.findByRole("group", { name: "Grafo de átomos" });
      fireEvent.pointerDown(head("infra"), { clientX: 10, clientY: 10, button: 0 });
      fireEvent.pointerUp(node("a1"), { clientX: 80, clientY: 80 });
      const menu = screen.getByRole("menu", { name: "Tipo de relación" });
      expect(within(menu).getAllByRole("menuitem")).toHaveLength(2); // condiciona y responsable_de admiten grupo de origen
      fireEvent.click(within(menu).getByRole("menuitem", { name: /responsable_de/ }));
      await waitFor(() => expect(createDocument).toHaveBeenCalledTimes(1));
      expect(createDocument.mock.calls[0]![0]).toBe("RelationDoc");
      expect(createDocument.mock.calls[0]![2]).toMatchObject({ source_id: "GrupoDoc:infra", target_id: "AtomDoc:a1", relation_type: "responsable_de" });
    });

    it("soltar sobre un grupo plegado abre el mismo menú (ya no rechaza)", async () => {
      mount({ documents: async () => withTypes });
      await screen.findByRole("group", { name: "Grafo de átomos" });
      fireEvent.click(screen.getByRole("button", { name: "Plegar grupo reuniones" }));
      fireEvent.pointerDown(node("a2"), { clientX: 10, clientY: 10, button: 0 });
      fireEvent.pointerUp(document.querySelector('[data-node-key="group:reuniones"]')!, { clientX: 80, clientY: 80 });
      expect(screen.getByRole("menu", { name: "Tipo de relación" })).toBeInTheDocument();
      expect(screen.queryByText(/despliégalo/)).toBeNull();
    });

    it("un 409 al crear el GrupoDoc se tolera y se crea la relación; otro error se muestra y no crea la relación", async () => {
      const conflict = Object.assign(new Error("409"), { status: 409 });
      const ok = vi.fn(async (model: string) => {
        if (model === "GrupoDoc") throw conflict;
        return { ok: true, id: "rel-1", version: "v" };
      });
      mount({ documents: async () => withTypes, createDocument: ok });
      await screen.findByRole("group", { name: "Grafo de átomos" });
      dropOnHead("a1", "reuniones");
      fireEvent.click(screen.getByRole("menuitem"));
      await waitFor(() => expect(ok).toHaveBeenCalledTimes(2));
      cleanup();

      const bad = vi.fn(async () => {
        throw Object.assign(new Error("boom"), { status: 500 });
      });
      mount({ documents: async () => withTypes, createDocument: bad });
      await screen.findByRole("group", { name: "Grafo de átomos" });
      dropOnHead("a1", "reuniones");
      fireEvent.click(screen.getByRole("menuitem"));
      expect(await screen.findByText(/No se creó la relación: boom/)).toBeInTheDocument();
      expect(bad).toHaveBeenCalledTimes(1);
    });

    it("no se relaciona un grupo con otro y el texto de ayuda ya no dice que no se puede", async () => {
      mount({ documents: async () => withTypes });
      await screen.findByRole("group", { name: "Grafo de átomos" });
      expect(screen.getByText(/Si sueltas sobre el encabezado de un grupo/)).toBeInTheDocument();
      fireEvent.pointerDown(head("infra"), { clientX: 10, clientY: 10, button: 0 });
      fireEvent.pointerUp(head("reuniones"), { clientX: 80, clientY: 80 });
      expect(screen.getByRole("alert")).toHaveTextContent(/No se relaciona un grupo con otro grupo/);
      expect(screen.queryByRole("menu")).toBeNull();
    });
  });
});
