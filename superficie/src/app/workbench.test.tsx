import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { parseWorkbenchHash, formatWorkbenchHash } from "./workbench-router";
import { WorkbenchShell, lensTargetView } from "./WorkbenchShell";
import type { SldbClient } from "../core/client";

function createFakeWorkbenchClient(): SldbClient {
  const fake = {
    schema: vi.fn().mockResolvedValue({ models: [] }),
    documents: vi.fn().mockResolvedValue([
      {
        id: "rep-01",
        model_name: "InformeDoc",
        path: "docs/rep-01.md",
        payload: { title: "Informe Principal" },
      },
      {
        id: "atom-01",
        model_name: "AtomDoc",
        path: "docs/atom-01.md",
        payload: {
          title: "Hallazgo 01",
          text: "Afirmación verificada desde fuente.",
          source: "FuenteDoc:src-01",
          quote: "anclaje de citas",
        },
      },
      {
        id: "src-01",
        model_name: "FuenteDoc",
        path: "docs/src-01.md",
        payload: {
          title: "Acta Primaria",
          body: "Contenido de prueba para anclaje de citas en fuente primaria.",
        },
      },
      {
        id: "spec-01",
        model_name: "SpecDoc",
        path: "docs/spec-01.md",
        payload: { title: "Árbol de Decisión" },
      },
    ]),
    modelsCatalog: vi.fn().mockResolvedValue([
      {
        name: "InformeDoc",
        model_ref: "models.InformeDoc",
        path: "models.py",
        version: 1,
        canonical: true,
        family: null,
        semantics: [],
        documents: 1,
      },
    ]),
    segments: vi.fn().mockResolvedValue({
      id: "InformeDoc:rep-01",
      doc: "rep-01",
      model: "InformeDoc",
      path: "docs/rep-01.md",
      text: "# Informe Principal\nTexto sintético del informe.",
      canonical: true,
      payload: {
        title: "Informe Principal",
        resumen: "Texto sintético del informe.",
      },
      segments: [
        { type: "literal", start: 0, end: 20, text: "# Informe Principal\n" },
        {
          type: "field",
          path: "resumen",
          marker: "rev",
          traits: [],
          editable: true,
          display: "block",
          source: null,
          children: [],
          start: 20,
          end: 48,
          text: "Texto sintético del informe.",
          value: "Texto sintético del informe.",
        },
      ],
    }),
    document: vi.fn().mockImplementation(async (id: string) => ({
      id,
      model_name: id.startsWith("src") ? "FuenteDoc" : "AtomDoc",
      path: `docs/${id}.md`,
      payload: {
        title: `Título ${id}`,
        text: "Afirmación verificada desde fuente.",
        source: "FuenteDoc:src-01",
        quote: "anclaje de citas",
        body: "Contenido de prueba para anclaje de citas en fuente primaria.",
      },
    })),
    notationView: vi.fn().mockResolvedValue({
      ok: true,
      spec: "spec-01",
      title: "Árbol de Decisión",
      diagram_type: "flowchart",
      notation: "clinical_flow",
      palette: "default",
      level: "summary",
      layout: { kind: "dagre", direction: "TB" },
      nodes: [
        {
          doc: "SpecNodeDoc:n1",
          element: "n1",
          title: "Evaluar basal",
          kind: "node",
          collection: "nodes",
          data: {},
          glyph: "state",
          shape: "rect",
          function: "entry",
          label: "Evaluar basal",
          label_style: "default",
          keyword: "STATE",
          compartments: [],
          markers: [],
          refs: ["AtomDoc:atom-01"],
          style: {},
        },
      ],
      links: [],
      fragments: [],
      skipped: [],
      legend: {
        glyphs: [
          {
            glyph: "state",
            title: "Estado",
            shape: "rect",
            function: "entry",
            style: {},
          },
        ],
        links: [],
        kinds: [],
      },
    }),
    getEdges: vi.fn().mockResolvedValue([]),
    describeModel: vi.fn().mockResolvedValue({
      name: "InformeDoc",
      model_ref: "models.InformeDoc",
      path: "models.py",
      version: 1,
      canonical: true,
      family: null,
      semantics: [],
      base_models: ["Document"],
      fields: [
        { name: "title", annotation: "str", description: "Título", default: null },
        { name: "resumen", annotation: "str", description: "Resumen", default: '""' },
      ],
      documents: [{ name: "rep-01", path: "docs/rep-01.md", semantic_tags: [] }],
      containment: {},
      references: [],
      compositions: {},
      semantics_map: {},
      authority: "authored",
      template: "# {title}\n\n{resumen}",
      has_draft: false,
      draft_path: null,
    }),
    rank: vi.fn().mockResolvedValue({
      status: "ok",
      hits: [],
    }),
  };
  return fake as unknown as SldbClient;
}

describe("workbench-router", () => {
  it("parses and formats workbench hash routes cleanly", () => {
    const parsed = parseWorkbenchHash("#/diagram?spec=SpecDoc%3Aspec-01&node=SpecNodeDoc%3An1");
    expect(parsed.view).toBe("diagram");
    expect(parsed.spec).toBe("SpecDoc:spec-01");
    expect(parsed.node).toBe("SpecNodeDoc:n1");

    const formatted = formatWorkbenchHash({
      view: "workbench",
      doc: "InformeDoc:rep-01",
      lens: "fierros",
    });
    expect(formatted).toBe("#/workbench?doc=InformeDoc%3Arep-01&lens=fierros");
  });

  it("keeps ?lens= on diagram and source routes so a reload does not lose it", () => {
    const diagram = formatWorkbenchHash({ view: "diagram", spec: "spec-01", lens: "fierros" });
    expect(diagram).toBe("#/diagram?lens=fierros&spec=spec-01");
    expect(parseWorkbenchHash(diagram)).toMatchObject({ view: "diagram", lens: "fierros", spec: "spec-01" });

    const source = formatWorkbenchHash({ view: "source", doc: "src-01", lens: "fierros" });
    expect(source).toBe("#/source?doc=src-01&lens=fierros");
    expect(parseWorkbenchHash(source)).toMatchObject({ view: "source", lens: "fierros", doc: "src-01" });

    expect(formatWorkbenchHash({ view: "studio", model: "InformeDoc", lens: "fierros" })).toBe("#/studio?model=InformeDoc");
  });
});

describe("WorkbenchShell", () => {
  const topbar = () => within(screen.getByTestId("wb-topbar"));
  const lens = (name: string | RegExp) => topbar().getByRole("button", { name });

  beforeEach(() => {
    window.history.replaceState(null, "", "#/");
  });

  it("renders the Stitch topbar without the 4 CRUD tabs", async () => {
    const client = createFakeWorkbenchClient();
    render(<WorkbenchShell client={client} />);

    await waitFor(() => {
      expect(screen.getByTestId("prosa-workbench-view")).toBeTruthy();
      expect(screen.getByTestId("sldb-sync-badge").textContent).toBe("[ Sincronizado con .sldb ]");
    });

    for (const tab of ["01. Prosa", "02. Spec2Viz", "03. Anclaje", "04. Studio"]) {
      expect(screen.queryByText(new RegExp(`^${tab}`))).toBeNull();
    }
    expect(screen.getByTestId("breadcrumb-doc-switch").textContent).toContain("rep-01");
    expect(topbar().getByText("InformeDoc")).toBeTruthy();
    expect(screen.getByTestId("wb-context-pill").textContent).toBe("prosa · lectura");
    expect(lens("[ Lectura ]").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("open-command-palette-btn").textContent).toBe("⌘K");
  });

  it("switches lenses with brackets and returns from studio to the document", async () => {
    const client = createFakeWorkbenchClient();
    render(<WorkbenchShell client={client} />);
    await waitFor(() => expect(screen.getByTestId("prosa-workbench-view")).toBeTruthy());

    fireEvent.click(lens("Estructura / Fierros"));
    await waitFor(() => expect(lens("[ Estructura / Fierros ]")).toBeTruthy());
    expect(screen.getByTestId("wb-context-pill").textContent).toBe("prosa · fierros visibles");

    fireEvent.click(lens("Esquema"));
    await waitFor(() => expect(screen.getByTestId("model-studio-view")).toBeTruthy());
    expect(lens("[ Esquema ]")).toBeTruthy();

    fireEvent.click(lens("Lectura"));
    await waitFor(() => expect(screen.getByTestId("prosa-workbench-view")).toBeTruthy());
    expect(lens("[ Lectura ]")).toBeTruthy();
  });

  it("reaches the 4 governed views through the topbar", async () => {
    const client = createFakeWorkbenchClient();
    render(<WorkbenchShell client={client} />);
    await waitFor(() => expect(screen.getByTestId("prosa-workbench-view")).toBeTruthy());

    fireEvent.click(lens("Spec2Viz ↗"));
    await waitFor(() => expect(screen.getByTestId("spec2viz-inspector-view")).toBeTruthy());
    expect(topbar().getByText("SpecDoc")).toBeTruthy();

    fireEvent.click(lens("Fuente ↗"));
    await waitFor(() => {
      expect(screen.getByTestId("source-anchoring-view")).toBeTruthy();
      expect(screen.getByTestId("prosemirror-source-viewer")).toBeTruthy();
    });
    expect(screen.getByTestId("breadcrumb-doc-switch").textContent).toContain("src-01");

    fireEvent.click(lens("Esquema"));
    await waitFor(() => {
      expect(screen.getByTestId("model-studio-view")).toBeTruthy();
      expect(screen.getByTestId("codemirror-template-editor")).toBeTruthy();
    });
  });

  it("the central lens selector holds only the 3 canonical Stitch lenses", async () => {
    const client = createFakeWorkbenchClient();
    render(<WorkbenchShell client={client} />);
    await waitFor(() => expect(screen.getByTestId("prosa-workbench-view")).toBeTruthy());
    const nav = within(screen.getByRole("navigation", { name: "Lentes del Workbench" }));
    const labels = nav.getAllByRole("button").map((b) => b.textContent);
    expect(labels).toEqual(["[ Lectura ]", "Estructura / Fierros", "Esquema"]);
    expect(nav.queryByText(/Spec2Viz|Fuente/)).toBeNull();
    // Los accesos rápidos viven en el área contextual derecha.
    expect(lens("Spec2Viz ↗")).toBeTruthy();
    expect(lens("Fuente ↗")).toBeTruthy();
  });

  it("Lectura / Fierros keep the diagram and source views; only studio returns to the prose", async () => {
    const client = createFakeWorkbenchClient();
    render(<WorkbenchShell client={client} />);
    await waitFor(() => expect(screen.getByTestId("prosa-workbench-view")).toBeTruthy());

    fireEvent.click(lens("Spec2Viz ↗"));
    await waitFor(() => expect(screen.getByTestId("spec2viz-inspector-view")).toBeTruthy());
    fireEvent.click(lens("Estructura / Fierros"));
    await waitFor(() => expect(lens("[ Estructura / Fierros ]")).toBeTruthy());
    expect(screen.getByTestId("spec2viz-inspector-view")).toBeTruthy();
    expect(screen.queryByTestId("prosa-workbench-view")).toBeNull();
    expect(window.location.hash).toMatch(/^#\/diagram/);

    fireEvent.click(lens("Fuente ↗"));
    await waitFor(() => expect(screen.getByTestId("source-anchoring-view")).toBeTruthy());
    fireEvent.keyDown(window, { key: "1" });
    await waitFor(() => expect(lens("[ Lectura ]")).toBeTruthy());
    expect(screen.getByTestId("source-anchoring-view")).toBeTruthy();

    fireEvent.click(lens("Esquema"));
    await waitFor(() => expect(screen.getByTestId("model-studio-view")).toBeTruthy());
    fireEvent.keyDown(window, { key: "2" });
    await waitFor(() => expect(screen.getByTestId("prosa-workbench-view")).toBeTruthy());
    expect(lens("[ Estructura / Fierros ]")).toBeTruthy();
  });

  it("lensTargetView: only studio falls back to the workbench", () => {
    expect(lensTargetView("workbench")).toBe("workbench");
    expect(lensTargetView("diagram")).toBe("diagram");
    expect(lensTargetView("source")).toBe("source");
    expect(lensTargetView("studio")).toBe("workbench");
  });

  it("the ⌘K palette uses Workbench tokens, not legacy accent colors", async () => {
    const client = createFakeWorkbenchClient();
    render(<WorkbenchShell client={client} />);
    await waitFor(() => expect(screen.getByTestId("prosa-workbench-view")).toBeTruthy());
    fireEvent.click(screen.getByTestId("open-command-palette-btn"));
    const palette = await screen.findByTestId("command-palette-modal");
    const label = within(palette).getByText("InformeDoc:rep-01");
    expect(label.getAttribute("style")).toContain("var(--wb-ink-muted)");
    expect(palette.innerHTML).not.toContain("--accent-blue");
  });

  it("real desk (no FuenteDoc/SpecDoc): Fuente reaches prose docs, Spec2Viz is hidden, palette opens prose", async () => {
    const client = createFakeWorkbenchClient();
    const real = [
      { id: "packaging", model_name: "PackagingDoc", path: "docs/packaging.md", payload: { title: "Packaging", body: "Instrucciones." } },
      { id: "arch-x", model_name: "ArchitectureNarrativeDoc", path: "docs/architecture/x.md", payload: { title: "Arquitectura X", body: "Texto de arquitectura." } },
      { id: "desk-spec", model_name: "DeskSpecDoc", path: "desk/SPEC.md", payload: { title: "SLDB Desk Surface Spec" } },
      { id: "atom-a", model_name: "AtomDoc", path: "desk/atoms/a.md", payload: { title: "A", answer: "a", provenance: "docs/architecture/x.md" } },
    ];
    (client.documents as ReturnType<typeof vi.fn>).mockResolvedValue(real);
    (client.document as ReturnType<typeof vi.fn>).mockImplementation(async (id: string) => real.find((d) => d.id === id));
    render(<WorkbenchShell client={client} />);
    await waitFor(() => expect(screen.getByTestId("prosa-workbench-view")).toBeTruthy());

    expect(topbar().queryByRole("button", { name: "Spec2Viz ↗" })).toBeNull();
    fireEvent.click(lens("Fuente ↗"));
    await waitFor(() => expect(screen.getByTestId("source-anchoring-view")).toBeTruthy());
    // El documento en lectura tiene prosa: Fuente lo abre a él; el breadcrumb no inventa "FuenteDoc".
    expect(screen.getByTestId("breadcrumb-doc-switch").textContent).toContain("packaging");
    expect(topbar().getByText("PackagingDoc")).toBeTruthy();
    const select = (await screen.findByLabelText("FuenteDoc")) as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.value)).toEqual(["arch-x", "packaging"]);
    expect(topbar().queryByText("FuenteDoc")).toBeNull();

    fireEvent.click(screen.getByTestId("open-command-palette-btn"));
    const palette = await screen.findByTestId("command-palette-modal");
    fireEvent.click(within(palette).getByText("PackagingDoc:packaging"));
    await waitFor(() => expect(screen.getByTestId("prosa-workbench-view")).toBeTruthy());
  });

  it("opens the Command Palette from the breadcrumb filtered by collection", async () => {
    const client = createFakeWorkbenchClient();
    render(<WorkbenchShell client={client} />);
    await waitFor(() => expect(screen.getByTestId("prosa-workbench-view")).toBeTruthy());

    fireEvent.click(screen.getByTestId("breadcrumb-doc-switch"));
    const palette = await screen.findByTestId("command-palette-modal");
    expect((within(palette).getByRole("textbox") as HTMLInputElement).value).toBe("InformeDoc");
  });

  it("base de un tutor en Lectura: la barra dice de quién es la configuración y esconde la maquinaria", async () => {
    const client = createFakeWorkbenchClient();
    (client.documents as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "atom-accion", model_name: "KnowledgeAtom", path: "knowledge/atom-accion.md", payload: { title: "La Acción" } },
      { id: "agent-tutor-apos", model_name: "AgentDoc", path: "agent/agent-tutor-apos.md", payload: { title: "Tutor APOS" } },
    ]);
    window.history.replaceState(null, "", "#/workbench");
    render(<WorkbenchShell client={client} />);

    expect((await screen.findByTestId("wiki-name")).textContent).toBe("Configuración · Tutor APOS");
    expect(document.title).toBe("Configuración · Tutor APOS");
    expect(topbar().queryByText("sldb")).toBeNull();
    expect(topbar().queryByText("AgentDoc")).toBeNull();
    expect(screen.queryByTestId("breadcrumb-doc-switch")).toBeNull();
    expect(screen.queryByTestId("wb-context-pill")).toBeNull();
    expect(screen.queryByTestId("sldb-sync-badge")).toBeNull();
    expect(screen.queryByTestId("open-command-palette-btn")).toBeNull();
    expect(topbar().queryByRole("button", { name: /contrato/ })).toBeNull();
    expect(topbar().queryByRole("button", { name: "Esquema" })).toBeNull();

    // Los fierros siguen a un clic (o tecla 2): ahí vuelve la barra de SLDB completa.
    fireEvent.click(screen.getByTestId("wiki-ver-estructura"));
    expect(screen.queryByTestId("wiki-name")).toBeNull();
    // Sin página pedida, se abre la de configuración, no la primera del store.
    expect(screen.getByTestId("breadcrumb-doc-switch").textContent).toContain("agent-tutor-apos");
    expect(topbar().getByText("AgentDoc")).toBeTruthy();
    expect(screen.getByTestId("wb-context-pill").textContent).toBe("prosa · fierros visibles");
    expect(lens("[ Estructura / Fierros ]").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("sldb-sync-badge").textContent).toBe("[ Sincronizado con .sldb ]");
    fireEvent.click(lens("Lectura"));
    expect(screen.getByTestId("wiki-name").textContent).toBe("Configuración · Tutor APOS");
  });

  it("does not claim sync when the store does not answer", async () => {
    const client = createFakeWorkbenchClient();
    (client.documents as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("SLDB respondió 502"));
    render(<WorkbenchShell client={client} />);
    await waitFor(() =>
      expect(screen.getByTestId("sldb-sync-badge").textContent).toBe("[ Sin conexión con .sldb ]"),
    );
  });
});
