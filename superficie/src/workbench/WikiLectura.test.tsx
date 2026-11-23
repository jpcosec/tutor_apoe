/**
 * La lente Lectura como wiki de un negocio: índice de páginas por tipo, agregar y quitar páginas
 * por `POST /save`, títulos legibles y el rechazo de SLDB junto al campo que falló.
 * Las formas (templates, semánticas, rutas, mensajes de error) son las del store de la peluquería.
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { SldbHttpError, type SldbClient } from "../core/client";
import type { DocumentSegments, FieldSegment, GraphDocument, ModelCatalogEntry, ModelDescription, SchemaResponse, Segment } from "../core/contract";
import { SldbProvider } from "../react/context";
import { ProsaWorkbenchView, type WorkbenchLens } from "./ProsaWorkbenchView";

// ---------- fixtures ----------

function segmentsOf(parts: (string | [path: string, text: string, over?: Partial<FieldSegment>])[]): Segment[] {
  let cursor = 0;
  return parts.map((part) => {
    const text = typeof part === "string" ? part : part[1];
    const base = { start: cursor, end: cursor + text.length, text };
    cursor += text.length;
    if (typeof part === "string") return { type: "literal" as const, ...base };
    return {
      type: "field" as const,
      ...base,
      value: text,
      path: part[0],
      marker: "rev",
      traits: [],
      editable: true,
      display: "inline" as const,
      source: null,
      children: [],
      ...part[2],
    };
  });
}

const servicioPayload = { nombre: "Corte de pelo hombre", duracion_min: 30, precio: 14000, descripcion: "Corte a tijera o máquina." };

const pages: Record<string, DocumentSegments> = {
  "corte-de-pelo-hombre": {
    id: "corte-de-pelo-hombre",
    doc: "corte-de-pelo-hombre",
    model: "ServicioDoc",
    path: "servicios/corte-de-pelo-hombre.md",
    text: "",
    canonical: true,
    payload: servicioPayload,
    segments: segmentsOf([
      "---\nnombre: ",
      ["nombre", "Corte de pelo hombre"],
      "\nduracion_min: ",
      ["duracion_min", "30", { value: 30, kind: "integer" }],
      "\nprecio: ",
      ["precio", "14000", { value: 14000, kind: "unknown" }],
      "\n---\n\n# ",
      ["nombre", "Corte de pelo hombre", { marker: "render", editable: false }],
      "\n\n",
      ["descripcion", "Corte a tijera o máquina.", { display: "block" }],
    ]),
  },
  horario: {
    id: "horario",
    doc: "horario",
    model: "HorarioDoc",
    path: "horario.md",
    text: "",
    canonical: true,
    payload: { cerrado: [], atencion: { lun: ["10:00-19:00"] } },
    segments: segmentsOf([
      "---\ncerrado:",
      ["cerrado", "", { value: [], kind: "list" }],
      "\n---\n\n# Horario\n\n## Atención\n\n```yaml\n",
      ["atencion", "lun:\n- 10:00-19:00", { value: { lun: ["10:00-19:00"] }, display: "block" }],
      "\n```",
    ]),
  },
};

const documents: GraphDocument[] = [
  { id: "negocio", model_name: "NegocioDoc", path: "negocio.md", payload: { nombre: "Peluquería Rayén" } },
  { id: "horario", model_name: "HorarioDoc", path: "horario.md", payload: pages.horario!.payload },
  { id: "balayage", model_name: "ServicioDoc", path: "servicios/balayage.md", payload: { nombre: "Balayage" } },
  { id: "corte-de-pelo-hombre", model_name: "ServicioDoc", path: "servicios/corte-de-pelo-hombre.md", payload: servicioPayload },
  { id: "rayen-soto", model_name: "ProfesionalDoc", path: "equipo/rayen-soto.md", payload: { nombre: "Rayén Soto" } },
];

const catalog = (name: string, type: string): ModelCatalogEntry => ({
  name,
  model_ref: `minegocio.paginas:${name}`,
  path: "paginas.py",
  version: 1,
  canonical: false,
  family: null,
  semantics: [`type.${type}`],
  documents: 0,
});

const models = [
  catalog("HorarioDoc", "negocio.horario"),
  catalog("NegocioDoc", "negocio.informacion-general"),
  catalog("ProfesionalDoc", "paquete.personal.profesional"),
  catalog("ServicioDoc", "paquete.catalogo.servicio"),
];

const schema: SchemaResponse = {
  models: [
    { id: "NegocioDoc", model_ref: "p:NegocioDoc", template: "# ⸢render•nombre⸥", fields: [{ name: "nombre", kind: "string", required: true }] },
    {
      id: "HorarioDoc",
      model_ref: "p:HorarioDoc",
      template: "---\ncerrado: ⸢rev,list•cerrado⸥\n---\n\n# Horario\n\n```yaml\n⸢rev,dict•atencion⸥\n```",
      fields: [
        { name: "cerrado", kind: "list", required: false },
        { name: "atencion", kind: "unknown", required: true },
      ],
    },
    {
      id: "ServicioDoc",
      model_ref: "p:ServicioDoc",
      template: "---\nnombre: ⸢rev•nombre⸥\n---\n\n# ⸢render•nombre⸥\n\n⸢rev,markdown•descripcion⸥",
      fields: [
        { name: "nombre", kind: "string", required: true, description: "Nombre del servicio como lo ve el cliente." },
        { name: "duracion_min", kind: "integer", required: true, description: "Cuánto dura la atención, en minutos." },
        { name: "precio", kind: "unknown", required: true },
        { name: "visible", kind: "boolean", required: false, default: true },
        { name: "descripcion", kind: "string", required: true },
      ],
    },
    { id: "ProfesionalDoc", model_ref: "p:ProfesionalDoc", template: "# ⸢render•nombre⸥", fields: [{ name: "nombre", kind: "string", required: true }] },
  ],
};

const RECHAZO =
  "corte-de-pelo-hombre: 1 validation error for ServicioDoc\nduracion_min\n  Input should be greater than or equal to 5 [type=greater_than_equal, input_value=2, input_type=int]";

function mount(over: { docId?: string; lens?: WorkbenchLens; docs?: GraphDocument[]; saveError?: Error } = {}) {
  const fake = {
    schema: vi.fn(async () => schema),
    segments: vi.fn(async (id: string) => {
      const page = pages[id];
      if (!page) throw new Error(`sin segmentos: ${id}`);
      return page;
    }),
    describeModel: vi.fn(async (name: string) => ({ name, model_ref: `minegocio.paginas:${name}`, authority: "authored" }) as unknown as ModelDescription),
    getEdges: vi.fn(async () => []),
    document: vi.fn(),
    save: vi.fn(async (_changes: unknown[]) => {
      if (over.saveError) throw over.saveError;
      return { ok: true };
    }),
  };
  const props = {
    docId: over.docId ?? "corte-de-pelo-hombre",
    lens: over.lens ?? ("lectura" as WorkbenchLens),
    documents: over.docs ?? documents,
    models,
    onSelectDoc: vi.fn(),
    onInspectDiagram: vi.fn(),
    onOpenSource: vi.fn(),
    onOpenStudio: vi.fn(),
    onDocumentsMutated: vi.fn(async () => undefined),
  };
  render(
    <SldbProvider client={fake as unknown as SldbClient}>
      <ProsaWorkbenchView {...props} />
    </SldbProvider>,
  );
  return { fake, props };
}

const index = () => within(screen.getByTestId("wiki-index"));
/** Espera a la página y al schema (los rótulos del índice salen de sus templates). */
async function ready(title: string) {
  expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe(title);
  await index().findByRole("button", { name: "Horario" });
}

// ---------- 1. índice ----------

describe("Wiki · índice del panel izquierdo", () => {
  it("lectura: índice por tipo en vez del mapa, con la página abierta marcada", async () => {
    mount();
    await ready("Corte de pelo hombre");
    expect(screen.queryByTestId("topology-mindmap")).toBeNull();
    expect(index().getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual(["Negocio", "Servicios", "Equipo"]);
    const negocio = within(screen.getByTestId("wiki-group-negocio"));
    expect(negocio.getAllByRole("button").map((b) => b.textContent)).toEqual(["Negocio", "Horario"]);
    const activa = index().getByRole("button", { current: "page" });
    expect(activa.textContent).toBe("Corte de pelo hombre");
  });

  it("elegir una página del índice navega a ella", async () => {
    const { props } = mount();
    await ready("Corte de pelo hombre");
    fireEvent.click(index().getByRole("button", { name: "Balayage" }));
    expect(props.onSelectDoc).toHaveBeenCalledWith("balayage");
  });

  it("fierros: se conserva el mapa y no hay índice", async () => {
    mount({ lens: "fierros" });
    await screen.findByTestId("topology-mindmap");
    expect(screen.queryByTestId("wiki-index")).toBeNull();
  });

  it("solo los tipos con varias páginas ofrecen «+ Agregar»", async () => {
    mount();
    await ready("Corte de pelo hombre");
    expect(index().getByRole("button", { name: "+ Agregar servicio" })).toBeTruthy();
    expect(index().getByRole("button", { name: "+ Agregar profesional" })).toBeTruthy();
    expect(within(screen.getByTestId("wiki-group-negocio")).queryByRole("button", { name: /Agregar/ })).toBeNull();
  });
});

// ---------- 2. crear y quitar ----------

describe("Wiki · agregar una página", () => {
  it("pide los campos obligatorios del tipo y crea con POST /save action=create", async () => {
    const { fake, props } = mount();
    await ready("Corte de pelo hombre");
    fireEvent.click(index().getByRole("button", { name: "+ Agregar servicio" }));
    const form = within(screen.getByTestId("nueva-pagina"));
    expect(form.getByRole("heading", { level: 1 }).textContent).toBe("Agregar servicio");
    // `visible` no es obligatorio: no se pide. La ayuda de cada campo es la descripción del schema.
    expect(form.queryByLabelText("Visible")).toBeNull();
    expect(form.getByText("Nombre del servicio como lo ve el cliente.")).toBeTruthy();
    fireEvent.change(form.getByLabelText("Nombre"), { target: { value: "Peinado de niña" } });
    fireEvent.change(form.getByLabelText("Duración (minutos)"), { target: { value: "45" } });
    fireEvent.change(form.getByLabelText("Precio"), { target: { value: "a cotizar" } });
    fireEvent.change(form.getByLabelText("Descripción"), { target: { value: "Trenzas y moños." } });
    fireEvent.click(form.getByRole("button", { name: "Crear página" }));
    await waitFor(() => expect(props.onSelectDoc).toHaveBeenCalledWith("peinado-de-nina"));
    expect(fake.save).toHaveBeenCalledWith([
      {
        id: "peinado-de-nina",
        action: "create",
        model: "ServicioDoc",
        payload: { nombre: "Peinado de niña", duracion_min: 45, precio: "a cotizar", descripcion: "Trenzas y moños." },
      },
    ]);
    expect(props.onDocumentsMutated).toHaveBeenCalled();
    expect(screen.queryByTestId("nueva-pagina")).toBeNull();
  });

  it("el rechazo de SLDB se muestra tal cual y la página no se da por creada", async () => {
    const error = new SldbHttpError("servicio: 1 validation error for ServicioDoc\nnombre\n  Field required", 422, null);
    const { props } = mount({ saveError: error });
    await ready("Corte de pelo hombre");
    fireEvent.click(index().getByRole("button", { name: "+ Agregar servicio" }));
    fireEvent.click(screen.getByRole("button", { name: "Crear página" }));
    const alert = await screen.findByTestId("nueva-pagina-error");
    expect(alert.getAttribute("role")).toBe("alert");
    expect(alert.textContent).toContain("1 validation error for ServicioDoc");
    expect(alert.textContent).toContain("Field required");
    expect(props.onSelectDoc).not.toHaveBeenCalled();
    expect(screen.getByTestId("nueva-pagina")).toBeTruthy();
  });

  it("cancelar vuelve a la página abierta sin escribir", async () => {
    const { fake } = mount();
    await ready("Corte de pelo hombre");
    fireEvent.click(index().getByRole("button", { name: "+ Agregar servicio" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByTestId("nueva-pagina")).toBeNull();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Corte de pelo hombre");
    expect(fake.save).not.toHaveBeenCalled();
  });

  it("wiki vacía: lo dice y ofrece la primera página de cada tipo; los obligatorios con estructura parten vacíos", async () => {
    const { fake, props } = mount({ docId: "", docs: [] });
    expect(screen.getByTestId("prosa-sin-paginas").textContent).toMatch(/todavía no tiene páginas/);
    fireEvent.click(await index().findByRole("button", { name: "+ Agregar horario" }));
    expect(index().getByRole("button", { name: "+ Agregar negocio" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Crear página" }));
    await waitFor(() => expect(props.onSelectDoc).toHaveBeenCalledWith("horario"));
    expect(fake.save).toHaveBeenCalledWith([{ id: "horario", action: "create", model: "HorarioDoc", payload: { atencion: {} } }]);
  });
});

describe("Wiki · quitar una página", () => {
  it("pide confirmación y quita con POST /save action=delete y el payload leído como expected", async () => {
    const { fake, props } = mount();
    await ready("Corte de pelo hombre");
    fireEvent.click(await screen.findByRole("button", { name: "Quitar esta página" }));
    expect(fake.save).not.toHaveBeenCalled();
    expect(screen.getByText(/¿Quitar «Corte de pelo hombre» de la wiki\?/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Sí, quitar" }));
    await waitFor(() => expect(props.onSelectDoc).toHaveBeenCalledWith("balayage"));
    expect(fake.save).toHaveBeenCalledWith([
      { id: "corte-de-pelo-hombre", action: "delete", model: "ServicioDoc", expected: servicioPayload },
    ]);
    expect(props.onDocumentsMutated).toHaveBeenCalled();
  });

  it("cancelar la confirmación no escribe nada", async () => {
    const { fake } = mount();
    await ready("Corte de pelo hombre");
    fireEvent.click(await screen.findByRole("button", { name: "Quitar esta página" }));
    fireEvent.click(within(screen.getByTestId("quitar-pagina")).getByRole("button", { name: "Cancelar" }));
    expect(screen.getByRole("button", { name: "Quitar esta página" })).toBeTruthy();
    expect(fake.save).not.toHaveBeenCalled();
  });

  it("si SLDB no la quita, muestra su mensaje", async () => {
    mount({ saveError: new SldbHttpError("corte-de-pelo-hombre cambió en SLDB. Recarga para evitar sobrescribirlo.", 409, null) });
    await ready("Corte de pelo hombre");
    fireEvent.click(await screen.findByRole("button", { name: "Quitar esta página" }));
    fireEvent.click(screen.getByRole("button", { name: "Sí, quitar" }));
    expect((await screen.findByTestId("quitar-pagina-error")).textContent).toContain("cambió en SLDB");
  });

  it("una página única (horario) no se puede quitar desde aquí", async () => {
    const { fake } = mount({ docId: "horario" });
    await ready("Horario");
    // Con la autoridad del modelo ya resuelta (que es lo que habilita quitar), sigue sin ofrecerse.
    await waitFor(() => expect(fake.describeModel).toHaveBeenCalledWith("HorarioDoc"));
    await screen.findByLabelText("Agregar a Atención: Lunes");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByTestId("quitar-pagina")).toBeNull();
  });
});

// ---------- 3. se lee como la wiki ----------

describe("Wiki · títulos y metadatos", () => {
  it("una página única se titula con el título de su template, no con su id; sin metadatos en lectura", async () => {
    mount({ docId: "horario" });
    await ready("Horario");
    expect(screen.queryByText(/HorarioDoc/)).toBeNull();
    expect(screen.queryByText(/path:/)).toBeNull();
  });

  it("fierros: la línea de modelo y path sigue ahí", async () => {
    mount({ docId: "horario", lens: "fierros" });
    expect(await screen.findByText(/HorarioDoc ·/)).toBeTruthy();
    expect(screen.getByText(/path: horario\.md/)).toBeTruthy();
  });

  it("una página con nombre se titula con él y el título se edita en el lugar", async () => {
    const { fake } = mount();
    await ready("Corte de pelo hombre");
    const h1 = screen.getByRole("heading", { level: 1 });
    fireEvent.click(await within(h1).findByRole("button", { name: "Corte de pelo hombre" }));
    const area = within(h1).getByRole("textbox");
    fireEvent.change(area, { target: { value: "Corte de pelo caballero" } });
    fireEvent.blur(area);
    await waitFor(() => expect(fake.save).toHaveBeenCalled());
    const [change] = fake.save.mock.calls[0]![0] as { action: string; payload: Record<string, unknown> }[];
    expect(change!.action).toBe("update");
    expect(change!.payload.nombre).toBe("Corte de pelo caballero");
  });
});

// ---------- 4. errores de guardado ----------

describe("Wiki · rechazo de un guardado", () => {
  it("queda en la fila del campo que falló, legible y con el texto del servidor sin tocar", async () => {
    mount({ saveError: new SldbHttpError(RECHAZO, 422, null) });
    await ready("Corte de pelo hombre");
    const campo = await screen.findByLabelText("Duración (minutos)");
    fireEvent.change(campo, { target: { value: "2" } });
    fireEvent.blur(campo);
    const alert = await screen.findByTestId("prosa-save-error");
    expect(alert.getAttribute("role")).toBe("alert");
    expect(alert.classList.contains("wb-mono")).toBe(false);
    expect(within(alert).getByText("No se guardó este cambio")).toBeTruthy();
    expect(alert.querySelector(".wb-aviso__mensaje")!.textContent).toBe(RECHAZO);
    // Está en la misma fila de la ficha que el campo, no en el encabezado.
    expect(alert.closest("dd")).toBe(campo.closest("dd"));
    expect(screen.getAllByTestId("prosa-save-error")).toHaveLength(1);
    fireEvent.click(within(alert).getByRole("button", { name: "Cerrar el aviso" }));
    expect(screen.queryByTestId("prosa-save-error")).toBeNull();
  });

  it("si falla el título (no está en la ficha), el aviso va bajo el título", async () => {
    mount({ saveError: new SldbHttpError("nombre: String should have at least 1 character", 422, null) });
    await ready("Corte de pelo hombre");
    const h1 = screen.getByRole("heading", { level: 1 });
    fireEvent.click(await within(h1).findByRole("button", { name: "Corte de pelo hombre" }));
    const area = within(h1).getByRole("textbox");
    fireEvent.change(area, { target: { value: "X" } });
    fireEvent.blur(area);
    const alert = await screen.findByTestId("prosa-save-error");
    expect(alert.closest("header")).not.toBeNull();
  });
});
