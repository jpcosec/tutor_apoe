import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { SldbClient } from "../core/client";
import type {
  AuthorityKind,
  CompositionPiece,
  DocumentSegments,
  Edge,
  FieldSegment,
  GraphDocument,
  LiteralSegment,
  ModelDescription,
  ResolvedNotationView,
  Segment,
} from "../core/contract";
import { SldbProvider } from "../react/context";
import { ProsaWorkbenchView, type WorkbenchLens } from "./ProsaWorkbenchView";

// ---------- fixtures ----------

let cursor = 0;
function literal(text: string): LiteralSegment {
  const seg = { type: "literal" as const, start: cursor, end: cursor + text.length, text };
  cursor += text.length;
  return seg;
}

function field(path: string, value: string, over: Partial<FieldSegment> = {}): FieldSegment {
  const seg: FieldSegment = {
    type: "field",
    start: cursor,
    end: cursor + value.length,
    text: value,
    value,
    path,
    marker: "rev",
    traits: [],
    editable: true,
    display: "block",
    source: null,
    children: [],
    ...over,
  };
  cursor += value.length;
  return seg;
}

function piece(path: string, ref: string, doc: string, sourcePath: string, text: string): CompositionPiece {
  const seg: CompositionPiece = {
    type: "composition",
    start: cursor,
    end: cursor + text.length,
    text,
    path,
    marker: "compose",
    traits: [],
    editable: true,
    display: "block",
    source: { doc, path: sourcePath, model: "AtomDoc" },
    children: [],
    ref_index: 0,
    ref,
  };
  cursor += text.length;
  return seg;
}

function informeSegments(): Segment[] {
  cursor = 0;
  return [
    literal("# Informe renal\n\nIntroducción literal que no es campo.\n\n## Resumen\n"),
    field("resumen", "Síntesis clínica ejecutiva."),
    literal("\n\nPárrafo literal de cierre.\n"),
    piece("criterios", "AtomDoc:atom-04", "AtomDoc:atom-04", "text", "texto de la pieza"),
  ];
}

const informe = (): DocumentSegments => ({
  id: "informe-1",
  doc: "informe-1",
  model: "InformeDoc",
  path: "docs/InformeDoc/informe-1.md",
  text: "",
  canonical: true,
  payload: { title: "Informe renal", estado: "Borrador", criterios: ["AtomDoc:atom-04"] },
  segments: informeSegments(),
});

const atom = (): DocumentSegments => ({
  id: "atom-04",
  doc: "atom-04",
  model: "AtomDoc",
  path: "docs/AtomDoc/atom-04.md",
  text: "",
  canonical: true,
  payload: { text: "Suspender el protocolo.", source: "FuenteDoc:src-1" },
  segments: [],
});

function describeOf(name: string, authority: AuthorityKind, modelRef: string): ModelDescription {
  return {
    name,
    model_ref: modelRef,
    path: `models/${name}.py`,
    version: 2,
    authority,
    base_models: [],
    fields: [
      { name: "title", annotation: "str", description: "" },
      { name: "resumen", annotation: "str", description: "" },
    ],
    compositions: {},
    references: [],
    template: "",
    has_draft: false,
  } as unknown as ModelDescription;
}

const documents: GraphDocument[] = [
  { id: "informe-1", model_name: "InformeDoc", path: "informe-1.md", payload: { title: "Informe renal" } },
  { id: "atom-04", model_name: "AtomDoc", path: "atom-04.md", payload: { title: "Criterio renal" } },
  { id: "diag", model_name: "SpecDoc", path: "diag.md", payload: { title: "Diagrama de flujo" } },
];

interface Setup {
  informeAuthority?: AuthorityKind;
  atomAuthority?: AuthorityKind;
  atomModelRef?: string;
  edges?: Edge[];
  /** Reemplaza el payload del informe (para probar ausencia de `estado`/`title`). */
  payload?: Record<string, unknown>;
  extraSegments?: (start: number) => Segment[];
  documents?: GraphDocument[];
  saveError?: Error;
  renderMarkdown?: string;
}

function makeClient(s: Setup = {}) {
  const fake = {
    segments: vi.fn(async (id: string) => {
      if (id === "informe-1") {
        const base = informe();
        return {
          ...base,
          payload: s.payload ?? base.payload,
          segments: [...base.segments, ...(s.extraSegments ? s.extraSegments(cursor) : [])],
        };
      }
      if (id === "atom-04") return atom();
      throw new Error(`sin segmentos: ${id}`);
    }),
    describeModel: vi.fn(async (name: string) =>
      name === "AtomDoc"
        ? describeOf("AtomDoc", s.atomAuthority ?? "authored", s.atomModelRef ?? "levira.models.AtomDoc")
        : describeOf(name, s.informeAuthority ?? "authored", `levira.models.${name}`),
    ),
    getEdges: vi.fn(async () => s.edges ?? []),
    document: vi.fn(),
    save: vi.fn(async (_changes: unknown[]) => {
      if (s.saveError) throw s.saveError;
      return {};
    }),
    render: vi.fn(async (_id: string) => {
      if (s.renderMarkdown === undefined) throw new Error("sin render");
      return s.renderMarkdown;
    }),
  };
  return { client: fake as unknown as SldbClient, fake };
}

function mount(lens: WorkbenchLens, s: Setup = {}) {
  const { client, fake } = makeClient(s);
  const props = {
    docId: "informe-1",
    lens,
    documents: s.documents ?? documents,
    models: [],
    onSelectDoc: vi.fn(),
    onInspectDiagram: vi.fn(),
    onOpenSource: vi.fn(),
    onOpenStudio: vi.fn(),
  };
  const utils = render(
    <SldbProvider client={client}>
      <ProsaWorkbenchView {...props} />
    </SldbProvider>,
  );
  return { ...utils, fake, props };
}

/** Espera a que el documento y la pieza transcluida estén cargados. */
async function ready() {
  await screen.findByText("Síntesis clínica ejecutiva.");
  await screen.findByText("Suspender el protocolo.");
}

// ---------- 1. layout y mindmap ----------

describe("ProsaWorkbenchView · layout", () => {
  it("usa .wb-split-38-62 con TopologyMindmap a la izquierda y la hoja a la derecha", async () => {
    mount("fierros");
    await ready();
    const root = screen.getByTestId("prosa-workbench-view");
    expect(root.classList.contains("wb-split-38-62")).toBe(true);
    const [left, right] = Array.from(root.children);
    expect(left!.classList.contains("wb-pane-left-38")).toBe(true);
    expect(within(left as HTMLElement).getByTestId("topology-mindmap")).toBeTruthy();
    expect(right!.classList.contains("wb-pane-right-62")).toBe(true);
  });

  it("el mindmap muestra ROOT con la clase del documento y sus hijos transcluidos", async () => {
    mount("fierros");
    await ready();
    const map = screen.getByTestId("topology-mindmap");
    expect(within(map).getByText("ROOT")).toBeTruthy();
    expect(within(map).getByText("class InformeDoc")).toBeTruthy();
    expect(within(map).getByText("id: informe-1")).toBeTruthy();
    expect(within(map).getByText(".criterios[0]")).toBeTruthy();
    expect(within(map).getByText("atom-04#text")).toBeTruthy();
  });

  it("el cajón schema lista los campos del modelo y abre el Studio", async () => {
    const { props } = mount("fierros");
    await ready();
    const pane = screen.getByTestId("topology-mindmap-pane");
    const schema = await within(pane).findByText("schema: InformeDoc");
    expect(within(pane).getByText("resumen:")).toBeTruthy();
    expect(within(pane).getAllByText("str").length).toBeGreaterThan(0);
    fireEvent.click(schema);
    expect(props.onOpenStudio).toHaveBeenCalledWith("InformeDoc");
  });

  it("muestra el error de carga dentro del split sin contenido de relleno", async () => {
    const { client, fake } = makeClient();
    fake.segments.mockRejectedValue(new Error("boom"));
    render(
      <SldbProvider client={client}>
        <ProsaWorkbenchView
          docId="informe-1"
          lens="lectura"
          documents={documents}
          models={[]}
          onSelectDoc={vi.fn()}
          onInspectDiagram={vi.fn()}
          onOpenSource={vi.fn()}
          onOpenStudio={vi.fn()}
        />
      </SldbProvider>,
    );
    expect(await screen.findByText(/Error al cargar informe-1: boom/)).toBeTruthy();
    expect(screen.getByTestId("prosa-workbench-view").classList.contains("wb-split-38-62")).toBe(true);
  });
});

// ---------- 2. literales de prosa (bug #1) ----------

describe("ProsaWorkbenchView · segmentos literales (bug #1)", () => {
  it.each<WorkbenchLens>(["lectura", "fierros"])("en lente %s no se pierde ningún literal", async (lens) => {
    mount(lens);
    await ready();
    const sheet = screen.getByTestId("prosa-workbench-view").querySelector(".wb-pane-right-62") as HTMLElement;
    expect(within(sheet).getByText("Introducción literal que no es campo.")).toBeTruthy();
    expect(within(sheet).getByText("Párrafo literal de cierre.")).toBeTruthy();
    expect(within(sheet).getByRole("heading", { level: 2, name: "Resumen" })).toBeTruthy();
    // El H1 del cuerpo no se duplica: el título vive solo en la cabecera.
    expect(within(sheet).getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(within(sheet).getByRole("heading", { level: 1 }).textContent).toBe("Informe renal");
  });

  it("los literales mantienen su orden respecto de los campos", async () => {
    mount("lectura");
    await ready();
    const text = screen.getByTestId("prosa-workbench-view").querySelector(".wb-pane-right-62")!.textContent ?? "";
    const order = ["Introducción literal", "Resumen", "Síntesis clínica", "Párrafo literal de cierre", "Suspender el protocolo"];
    const positions = order.map((s) => text.indexOf(s));
    expect(positions.every((p) => p >= 0)).toBe(true);
    expect([...positions].sort((a, b) => a - b)).toEqual(positions);
  });
});

// ---------- 3. lentes ----------

describe("ProsaWorkbenchView · lentes", () => {
  it("lectura: sin gutter marginal ni etiquetas de transclusión", async () => {
    const { container } = mount("lectura");
    await ready();
    expect(container.querySelectorAll(".wb-marginal-gutter")).toHaveLength(0);
    expect(container.querySelectorAll(".wb-transclusion-card__header")).toHaveLength(0);
    expect(screen.queryByText(/transclude:/)).toBeNull();
    expect(screen.queryByText(/AtomDoc · editable in-place/)).toBeNull();
    expect(container.querySelector(".wb-editorial-sheet--lectura")).toBeTruthy();
    expect(container.querySelectorAll(".wb-block-with-gutter--lectura").length).toBeGreaterThan(0);
  });

  it("fierros: gutter con field/transclude y encabezado de la tarjeta transcluida", async () => {
    const { container } = mount("fierros");
    await ready();
    const gutters = Array.from(container.querySelectorAll(".wb-marginal-gutter")).map((g) => g.textContent);
    expect(gutters).toContain("field: resumen");
    expect(gutters).toContain("transclude: atom-04#text");
    const header = container.querySelector(".wb-transclusion-card__header") as HTMLElement;
    expect(header.textContent).toMatch(/atom-04\.md → #text \(AtomDoc · editable in-place\)/);
    expect(container.querySelector(".wb-editorial-sheet")).toBeTruthy();
  });

  it("fierros: la tarjeta navega al átomo y a su fuente", async () => {
    const { container, props } = mount("fierros");
    await ready();
    const header = container.querySelector(".wb-transclusion-card__header") as HTMLElement;
    fireEvent.click(within(header).getByText("↗"));
    expect(props.onSelectDoc).toHaveBeenCalledWith("atom-04");
    fireEvent.click(within(header).getByText("[src-1]"));
    expect(props.onOpenSource).toHaveBeenCalledWith("src-1");
  });
});

// ---------- 4. autoridad (bug #2) y "Conectado con" ----------

describe("ProsaWorkbenchView · autoridad de transclusiones (bug #2)", () => {
  it("átomo authored local: editable in-place y el commit va al documento hijo", async () => {
    const { container, fake } = mount("fierros");
    await ready();
    await waitFor(() =>
      expect(container.querySelector(".wb-transclusion-card__header")!.textContent).toMatch(/editable in-place/),
    );
    const quote = container.querySelector(".wb-transclusion-card__quote") as HTMLElement;
    fireEvent.click(within(quote).getByRole("button"));
    const area = within(quote).getByRole("textbox");
    fireEvent.change(area, { target: { value: "Suspender de inmediato." } });
    fireEvent.blur(area);
    await waitFor(() => expect(fake.save).toHaveBeenCalled());
    const [change] = fake.save.mock.calls[0]![0] as unknown as { id: string; model: string; payload: Record<string, unknown> }[];
    expect(change!.id).toBe("atom-04");
    expect(change!.model).toBe("AtomDoc");
    expect(change!.payload.text).toBe("Suspender de inmediato.");
  });

  it.each<[string, Setup]>([
    ["source_raw", { atomAuthority: "source_raw" }],
    ["theorem", { atomAuthority: "theorem" }],
    ["generated", { atomAuthority: "generated" }],
    ["dueño deskops", { atomModelRef: "deskops.models.AtomDoc" }],
  ])("átomo %s: read-only, sin edición in-place", async (_label, setup) => {
    const { container, fake } = mount("fierros", setup);
    await ready();
    await waitFor(() =>
      expect(container.querySelector(".wb-transclusion-card__header")!.textContent).toMatch(/AtomDoc · read-only/),
    );
    const quote = container.querySelector(".wb-transclusion-card__quote") as HTMLElement;
    expect(within(quote).queryByRole("button")).toBeNull();
    expect(fake.save).not.toHaveBeenCalled();
  });

  it("la autoridad del modelo padre controla también sus campos de prosa", async () => {
    const { container } = mount("fierros", { informeAuthority: "theorem" });
    await ready();
    await waitFor(() => expect(container.querySelector(".wb-block-with-gutter--editable")).toBeNull());
    expect(screen.getByText("Síntesis clínica ejecutiva.").getAttribute("role")).toBeNull();
  });

  it("modelo padre authored: el campo de prosa es editable", async () => {
    const { container } = mount("fierros");
    await ready();
    await waitFor(() => expect(container.querySelector(".wb-block-with-gutter--editable")).toBeTruthy());
    expect(screen.getByText("Síntesis clínica ejecutiva.").getAttribute("role")).toBe("button");
  });
});

describe("ProsaWorkbenchView · Conectado con", () => {
  it("consulta client.getEdges con el id global del documento y lista los vecinos por título", async () => {
    const edges: Edge[] = [
      { id: "e1", source: "InformeDoc:informe-1", target: "AtomDoc:atom-04", type: "compose" },
      { id: "e2", source: "SpecDoc:diag", target: "InformeDoc:informe-1", type: "reference" },
    ] as Edge[];
    const { fake } = mount("lectura", { edges });
    await ready();
    expect(fake.getEdges).toHaveBeenCalledWith("InformeDoc:informe-1");
    const footer = (await screen.findByText("Conectado con")).closest("footer") as HTMLElement;
    expect(within(footer).getByText("Criterio renal")).toBeTruthy();
    expect(within(footer).getByText("Diagrama de flujo")).toBeTruthy();
    expect(within(footer).queryByText("Informe renal")).toBeNull();
  });

  it("sin aristas no inventa el pie", async () => {
    const { fake } = mount("lectura");
    await ready();
    await waitFor(() => expect(fake.getEdges).toHaveBeenCalled());
    expect(screen.queryByText("Conectado con")).toBeNull();
  });
});

// ---------- ronda 2 del Concilio: B3, B4, B5 ----------

const versioned: GraphDocument[] = documents.map((d) =>
  d.id === "informe-1" ? { ...d, version: "abcdef0123456789" } : d,
);

function specView(): ResolvedNotationView {
  return {
    spec: "SpecDoc:diag",
    title: "Diagrama de flujo",
    diagram_type: "activity",
    notation: "activity",
    palette: "default",
    level: "x",
    layout: { kind: "layered", direction: "TB" },
    nodes: [
      {
        doc: "diag.inicio",
        element: "inicio",
        title: "Inicio",
        kind: "step",
        collection: "nodes",
        data: {},
        glyph: "GlyphDoc:activity.initial",
        shape: "circle",
        function: "entry",
        label: "Inicio",
        label_style: "",
        keyword: "",
        compartments: [],
        markers: [],
        refs: [],
        style: {},
      },
    ],
    links: [],
    fragments: [],
    skipped: [],
    legend: { glyphs: [], links: [], kinds: [] },
  };
}

describe("ProsaWorkbenchView · B3 errores de guardado y expected", () => {
  it("un error al guardar se muestra como alerta junto al campo que falló, con el mensaje del servidor", async () => {
    mount("fierros", { saveError: new Error("SLDB respondió 500") });
    await ready();
    fireEvent.click(await screen.findByRole("button", { name: "Síntesis clínica ejecutiva." }));
    const area = screen.getByRole("textbox");
    fireEvent.change(area, { target: { value: "Otra síntesis." } });
    fireEvent.blur(area);
    const alert = await screen.findByTestId("prosa-save-error");
    expect(alert.getAttribute("role")).toBe("alert");
    expect(alert.textContent).toMatch(/No se guardó este cambio.*SLDB respondió 500/);
    // El aviso queda en el bloque del field `resumen`, no en el encabezado de la página.
    expect(alert.closest(".wb-block-with-gutter")?.textContent).toContain("field: resumen");
    expect(alert.closest("header")).toBeNull();
    expect(screen.queryByText(/✓ sincronizado/)).toBeNull();
  });

  it("fierros: los campos editables muestran POST /save · expected <hash7>", async () => {
    const { container } = mount("fierros", { documents: versioned });
    await ready();
    await waitFor(() => expect(container.querySelector(".wb-block-with-gutter--editable")).toBeTruthy());
    const subs = Array.from(container.querySelectorAll(".wb-marginal-gutter__sub")).map((n) => n.textContent);
    expect(subs).toEqual(["POST /save · expected abcdef0"]);
    expect(subs[0]).not.toContain("abcdef01");
  });

  it("sin versión conocida o con campo de solo lectura no inventa el expected", async () => {
    const first = mount("fierros");
    await ready();
    expect(first.container.querySelectorAll(".wb-marginal-gutter__sub")).toHaveLength(0);
    first.unmount();

    const second = mount("fierros", { documents: versioned, informeAuthority: "theorem" });
    await ready();
    await waitFor(() => expect(second.fake.describeModel).toHaveBeenCalledWith("InformeDoc"));
    await waitFor(() => expect(second.container.querySelectorAll(".wb-marginal-gutter__sub")).toHaveLength(0));
  });

  it("lectura: nunca muestra la línea de expected", async () => {
    const { container } = mount("lectura", { documents: versioned });
    await ready();
    expect(container.querySelectorAll(".wb-marginal-gutter__sub")).toHaveLength(0);
  });
});

describe("ProsaWorkbenchView · B4 título editable", () => {
  it("con autoridad editable y `title` en el payload, el h1 se edita y guarda title", async () => {
    const { fake } = mount("lectura");
    await ready();
    const h1 = screen.getByRole("heading", { level: 1 });
    fireEvent.click(await within(h1).findByRole("button", { name: "Informe renal" }));
    const area = within(h1).getByRole("textbox");
    fireEvent.change(area, { target: { value: "Informe renal revisado" } });
    fireEvent.blur(area);
    await waitFor(() => expect(fake.save).toHaveBeenCalled());
    const [change] = fake.save.mock.calls[0]![0] as unknown as { id: string; payload: Record<string, unknown> }[];
    expect(change!.id).toBe("informe-1");
    expect(change!.payload.title).toBe("Informe renal revisado");
  });

  it("autoridad no editable: el h1 queda como texto", async () => {
    mount("lectura", { informeAuthority: "source_raw" });
    await ready();
    const h1 = screen.getByRole("heading", { level: 1 });
    await waitFor(() => expect(within(h1).queryByRole("button")).toBeNull());
    expect(h1.textContent).toBe("Informe renal");
  });

  it("sin `title` en el payload: el h1 muestra el título literal de la página, no su id, y no es editable", async () => {
    mount("lectura", { payload: { criterios: ["AtomDoc:atom-04"] } });
    await ready();
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toBe("Informe renal");
    expect(within(h1).queryByRole("button")).toBeNull();
  });
});

describe("ProsaWorkbenchView · B5 sin datos inventados", () => {
  it("lectura: no muestra la línea de metadatos (modelo, estado, path)", async () => {
    mount("lectura");
    await ready();
    expect(screen.queryByText(/InformeDoc ·/)).toBeNull();
    expect(screen.queryByText(/path:/)).toBeNull();
  });

  it("fierros: muestra el estado solo si el payload lo trae", async () => {
    mount("fierros");
    await ready();
    expect(screen.getByText(/InformeDoc · Borrador ·/)).toBeTruthy();
  });

  it("sin status/estado no inventa 'En revisión'", async () => {
    mount("fierros", { payload: { title: "Informe renal" } });
    await ready();
    expect(screen.queryByText(/En revisión/)).toBeNull();
    expect(screen.getByText(/^InformeDoc ·$/)).toBeTruthy();
  });

  it("la tabla rotula su kind/marker real, no 'MarkdownTable (rev)' fijo", async () => {
    mount("fierros", {
      extraSegments: (start) => [
        field("dosis", "", {
          start,
          end: start,
          marker: "render",
          kind: "stringlist",
          table_data: { columns: ["droga", "dosis"], rows: [{ droga: "X", dosis: "10 mg" }] },
        }),
      ],
    });
    await ready();
    expect(await screen.findByText("10 mg")).toBeTruthy();
    expect(screen.queryByText("MarkdownTable (rev)")).toBeNull();
    expect(screen.getByText("stringlist · render")).toBeTruthy();
  });

  it("[ Fuente YAML/MD ] consulta client.render y muestra el markdown real del SpecDoc", async () => {
    const md = "---\nnotation: activity\n---\n# Diagrama de flujo\n- inicio";
    const { fake } = mount("fierros", {
      renderMarkdown: md,
      extraSegments: (start) => [field("diagrama_flujo", "SpecDoc:diag", { start, end: start, marker: "render", projection: specView() })],
    });
    await ready();
    expect(await screen.findByTestId("notation-svg")).toBeTruthy();
    expect(fake.render).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Fuente YAML/MD" }));
    const raw = await screen.findByTestId("spec2viz-raw-source");
    expect(fake.render).toHaveBeenCalledWith("diag");
    expect(raw.textContent).toBe(md);
    expect(raw.textContent).not.toMatch(/"nodes":/);
  });

  it("si client.render falla, lo dice en vez de mostrar un resumen inventado", async () => {
    mount("fierros", {
      extraSegments: (start) => [field("diagrama_flujo", "SpecDoc:diag", { start, end: start, marker: "render", projection: specView() })],
    });
    await ready();
    fireEvent.click(await screen.findByRole("button", { name: "Fuente YAML/MD" }));
    expect((await screen.findByText(/No se pudo leer el SpecDoc \(diag\)/)).getAttribute("role")).toBe("alert");
  });
});

describe("ProsaWorkbenchView · autoridad pendiente", () => {
  it("la transclusión es de solo lectura mientras describeModel no resuelve", async () => {
    const { client, fake } = makeClient();
    let resolveAtom: (d: ModelDescription) => void = () => {};
    fake.describeModel.mockImplementation(async (name: string) => {
      if (name !== "AtomDoc") return describeOf(name, "authored", `levira.models.${name}`);
      return new Promise<ModelDescription>((r) => {
        resolveAtom = r;
      });
    });
    const { container } = render(
      <SldbProvider client={client}>
        <ProsaWorkbenchView
          docId="informe-1"
          lens="fierros"
          documents={documents}
          models={[]}
          onSelectDoc={vi.fn()}
          onInspectDiagram={vi.fn()}
          onOpenSource={vi.fn()}
          onOpenStudio={vi.fn()}
        />
      </SldbProvider>,
    );
    await ready();
    await waitFor(() => expect(fake.describeModel).toHaveBeenCalledWith("AtomDoc"));
    const quote = () => container.querySelector(".wb-transclusion-card__quote") as HTMLElement;
    expect(container.querySelector(".wb-transclusion-card__header")!.textContent).toMatch(/AtomDoc · read-only/);
    expect(within(quote()).queryByRole("button")).toBeNull();

    resolveAtom(describeOf("AtomDoc", "authored", "levira.models.AtomDoc"));
    await waitFor(() => expect(within(quote()).getByRole("button")).toBeTruthy());
    expect(container.querySelector(".wb-transclusion-card__header")!.textContent).toMatch(/editable in-place/);
  });

  it("si describeModel falla, la transclusión sigue de solo lectura", async () => {
    const { client, fake } = makeClient();
    fake.describeModel.mockImplementation(async (name: string) => {
      if (name === "AtomDoc") throw new Error("sin contrato");
      return describeOf(name, "authored", `levira.models.${name}`);
    });
    const { container } = render(
      <SldbProvider client={client}>
        <ProsaWorkbenchView
          docId="informe-1"
          lens="fierros"
          documents={documents}
          models={[]}
          onSelectDoc={vi.fn()}
          onInspectDiagram={vi.fn()}
          onOpenSource={vi.fn()}
          onOpenStudio={vi.fn()}
        />
      </SldbProvider>,
    );
    await ready();
    await waitFor(() => expect(fake.describeModel).toHaveBeenCalledWith("AtomDoc"));
    const quote = container.querySelector(".wb-transclusion-card__quote") as HTMLElement;
    expect(within(quote).queryByRole("button")).toBeNull();
  });
});
