import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { SldbClient } from "../core/client";
import type { GraphDocument, NotationLink, NotationNode, ResolvedNotationView } from "../core/contract";
import { layoutNotation } from "./NotationSvgCanvas";
import { Spec2VizInspectorView } from "./Spec2VizInspectorView";

function node(element: string, over: Partial<NotationNode> = {}): NotationNode {
  return {
    doc: `spec.${element}`,
    element,
    title: element,
    kind: "step",
    collection: "nodes",
    data: {},
    glyph: "GlyphDoc:activity.step",
    shape: "rounded-box",
    function: "",
    label: element,
    label_style: "",
    keyword: "",
    compartments: [],
    markers: [],
    refs: [],
    style: {},
    ...over,
  };
}

function viewOf(nodes: NotationNode[], links: NotationLink[]): ResolvedNotationView {
  return {
    spec: "spec",
    title: "Spec",
    diagram_type: "activity",
    notation: "activity",
    palette: "default",
    level: "x",
    layout: { kind: "layered", direction: "TB" },
    nodes,
    links,
    fragments: [],
    skipped: [],
    legend: { glyphs: [], links: [], kinds: [] },
  };
}

const nodes = [
  node("ingreso", { function: "entry" }),
  node("check", { shape: "diamond", kind: "decision", function: "decision", refs: ["AtomDoc:atom-04", "PythonSymbolDoc:rules.check"] }),
  node("suspension"),
  node("titulacion"),
  node("fin", { function: "exit" }),
  node("suelto"),
];
const links: NotationLink[] = [
  { source: "ingreso", target: "check", relation: "next" },
  { source: "check", target: "suspension", relation: "branch", label: "Sí" },
  { source: "check", target: "titulacion", relation: "branch", label: "No" },
  { source: "suspension", target: "fin", relation: "next" },
];

const documents: GraphDocument[] = [
  { id: "spec", model_name: "SpecDoc", path: "spec.md", payload: { title: "Spec" } },
  {
    id: "atom-04",
    model_name: "AtomDoc",
    path: "atom-04.md",
    payload: { quote: "Suspender el protocolo.", source: "FuenteDoc:src-1" },
  },
  { id: "rules.check", model_name: "PythonSymbolDoc", path: "src/rules.py", payload: {} },
];

function fakeClient(view: ResolvedNotationView): SldbClient {
  return {
    notationView: vi.fn().mockResolvedValue(view),
    getEdges: vi.fn().mockResolvedValue([]),
    document: vi.fn().mockRejectedValue(new Error("no")),
  } as unknown as SldbClient;
}

function renderView(view: ResolvedNotationView, activeNodeDoc: string | null, extra: Record<string, unknown> = {}) {
  const props = {
    client: fakeClient(view),
    documents,
    activeSpecId: "spec",
    activeNodeDoc,
    onSelectSpec: vi.fn(),
    onSelectNode: vi.fn(),
    onNavigateToDoc: vi.fn(),
    onNavigateToSource: vi.fn(),
    ...extra,
  };
  render(<Spec2VizInspectorView {...props} />);
  return props;
}

describe("layoutNotation", () => {
  it("asigna niveles por camino más largo y abre ramas en horizontal", () => {
    const l = layoutNotation(viewOf(nodes, links));
    expect(l.levels).toEqual([["ingreso"], ["check"], ["suspension", "titulacion"], ["fin"], ["suelto"]]);
    const [a, b] = l.nodes.filter((n) => n.level === 2);
    expect(a!.y).toBe(b!.y);
    expect(a!.x).toBeLessThan(b!.x);
    expect(l.edges).toHaveLength(4);
  });

  it("no inventa enlaces cuando view.links está vacío y no descarta nodos", () => {
    const l = layoutNotation(viewOf(nodes, []));
    expect(l.edges).toHaveLength(0);
    expect(l.nodes).toHaveLength(nodes.length);
  });
});

describe("NotationSvgCanvas", () => {
  it("dibuja ● inicial, ◉ terminal y rombo de decisión según lo que declara cada nodo", async () => {
    renderView(viewOf(nodes, links), "spec.suspension");
    await waitFor(() => expect(screen.getByTestId("notation-svg")).toBeTruthy());
    const ini = screen.getByTestId("diagram-node-ingreso");
    expect(ini.getAttribute("data-node-type")).toBe("initial");
    expect(ini.querySelectorAll("circle")).toHaveLength(1);
    const fin = screen.getByTestId("diagram-node-fin");
    expect(fin.getAttribute("data-node-type")).toBe("terminal");
    expect(fin.querySelectorAll("circle")).toHaveLength(2);
    expect(screen.getByTestId("diagram-node-check").querySelector("polygon")).toBeTruthy();
    // El badge oscuro solo acompaña al rombo seleccionado.
    expect(screen.queryByTestId("node-badge")).toBeNull();
  });
});

describe("Spec2VizInspectorView", () => {
  it("no dibuja aristas falsas Sí/No sin links", async () => {
    renderView(viewOf(nodes.slice(0, 3), []), "spec.check");
    await waitFor(() => expect(screen.getByTestId("notation-svg")).toBeTruthy());
    expect(screen.queryAllByTestId("notation-edge")).toHaveLength(0);
    expect(screen.queryByText("Sí")).toBeNull();
    expect(screen.getByText("sin enlaces en view.links")).toBeTruthy();
  });

  it("dibuja aristas reales con su etiqueta y el badge del nodo de decisión", async () => {
    renderView(viewOf(nodes, links), "spec.check");
    await waitFor(() => expect(screen.getAllByTestId("notation-edge")).toHaveLength(4));
    expect(screen.getByTestId("node-badge").textContent).toBe("SpecNodeDoc: .check · 1 atoms · 1 ref");
  });

  it("separa atom_refs (solo AtomDoc) de refs (el resto)", async () => {
    const props = renderView(viewOf(nodes, links), "spec.check");
    const atoms = await screen.findByTestId("section-atom-refs");
    expect(within(atoms).getAllByTestId("atom-card")).toHaveLength(1);
    expect(within(atoms).getByText("“Suspender el protocolo.”")).toBeTruthy();
    expect(within(atoms).getByText(/atom-04\.md → #quote \(AtomDoc · transcluded\)/)).toBeTruthy();
    expect(within(atoms).queryByText(/PythonSymbolDoc/)).toBeNull();
    const refs = screen.getByTestId("section-refs");
    expect(within(refs).getByText("PythonSymbolDoc")).toBeTruthy();
    expect(within(refs).queryByText(/atom-04/)).toBeNull();

    fireEvent.click(within(atoms).getByText("↗ atom-04"));
    expect(props.onNavigateToDoc).toHaveBeenCalledWith("atom-04");
    fireEvent.click(within(atoms).getByText("fuente: FuenteDoc:src-1"));
    expect(props.onNavigateToSource).toHaveBeenCalledWith("src-1");
  });

  it("una ref sin prefijo AtomDoc: cuyo documento es AtomDoc cuenta como átomo en sección y badge", async () => {
    const bare = nodes.map((n) => (n.element === "check" ? { ...n, refs: ["Atom:atom-04", "PythonSymbolDoc:rules.check"] } : n));
    renderView(viewOf(bare, links), "spec.check");
    const atoms = await screen.findByTestId("section-atom-refs");
    expect(within(atoms).getAllByTestId("atom-card")).toHaveLength(1);
    expect(within(screen.getByTestId("section-refs")).queryByText(/atom-04/)).toBeNull();
    expect(screen.getByTestId("node-badge").textContent).toBe("SpecNodeDoc: .check · 1 atoms · 1 ref");
  });

  it("lista enlaces inbound y outbound desde view.links", async () => {
    renderView(viewOf(nodes, links), "spec.check");
    const section = await screen.findByTestId("section-edges");
    expect(within(section).getAllByTestId("edge-inbound")).toHaveLength(1);
    expect(within(section).getAllByTestId("edge-outbound")).toHaveLength(2);
    expect(within(section).getByText("SpecNodeDoc:spec.ingreso")).toBeTruthy();
    expect(within(section).getByText("SpecNodeDoc:spec.titulacion")).toBeTruthy();
  });

  it("solo SpecDoc es diagrama: DeskSpecDoc del desk real no se manda a /notations/view", async () => {
    const desk: GraphDocument[] = [
      { id: "desk-spec", model_name: "DeskSpecDoc", path: "desk/SPEC.md", payload: { title: "SLDB Desk Surface Spec" } },
      { id: "faq", model_name: "FAQDoc", path: "docs/faq.md", payload: { title: "FAQ" } },
    ];
    const client = fakeClient(viewOf(nodes, links));
    render(
      <Spec2VizInspectorView
        client={client}
        documents={desk}
        activeSpecId={null}
        activeNodeDoc={null}
        onSelectSpec={vi.fn()}
        onSelectNode={vi.fn()}
        onNavigateToDoc={vi.fn()}
        onNavigateToSource={vi.fn()}
      />,
    );
    expect(await screen.findByText("No hay SpecDoc en el store.")).toBeTruthy();
    expect(client.notationView).not.toHaveBeenCalled();

    render(
      <Spec2VizInspectorView
        client={client}
        documents={[...desk, ...documents]}
        activeSpecId={null}
        activeNodeDoc={null}
        onSelectSpec={vi.fn()}
        onSelectNode={vi.fn()}
        onNavigateToDoc={vi.fn()}
        onNavigateToSource={vi.fn()}
      />,
    );
    await waitFor(() => expect(client.notationView).toHaveBeenCalledWith("spec"));
    expect(client.notationView).not.toHaveBeenCalledWith("desk-spec");
  });

  it("muestra el error de carga sin contenido de relleno", async () => {
    const client = { notationView: vi.fn().mockRejectedValue(new Error("boom")), getEdges: vi.fn() } as unknown as SldbClient;
    render(
      <Spec2VizInspectorView
        client={client}
        documents={documents}
        activeSpecId="spec"
        activeNodeDoc={null}
        onSelectSpec={vi.fn()}
        onSelectNode={vi.fn()}
        onNavigateToDoc={vi.fn()}
        onNavigateToSource={vi.fn()}
      />,
    );
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText(/boom/)).toBeTruthy();
  });
});

describe("Spec2Viz con datos reales del store", () => {
  it("wrapLabel parte en dos líneas y elide solo lo que no cabe", async () => {
    const { wrapLabel } = await import("./NotationSvgCanvas");
    expect(wrapLabel("Receive SPEC paths from CLI args", 24)).toEqual(["Receive SPEC paths from", "CLI args"]);
    expect(wrapLabel("corto", 24)).toEqual(["corto"]);
    const long = wrapLabel("uno dos tres cuatro cinco seis siete ocho nueve diez", 12);
    expect(long).toHaveLength(2);
    expect(long[1]!.endsWith("…")).toBe(true);
  });

  it("no duplica el prefijo SpecNodeDoc cuando node.doc ya lo trae", async () => {
    const { qualifiedNodeDoc } = await import("./Spec2VizInspectorView");
    expect(qualifiedNodeDoc("SpecNodeDoc:activity.x.receive_paths")).toBe("SpecNodeDoc:activity.x.receive_paths");
    expect(qualifiedNodeDoc("n1")).toBe("SpecNodeDoc:n1");
  });
});

