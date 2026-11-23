import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { SldbClient } from "../core/client";
import type { GraphDocument } from "../core/contract";
import { computeCoverage } from "./anchoring-coverage";
import {
  SourceAnchoringView,
  atomBelongsToSource,
  downstreamLinks,
  isAnchorableSource,
  rankSources,
  storedOffsets,
} from "./SourceAnchoringView";
import type { Edge } from "../core/contract";

const BODY = "Alfa beta gamma delta epsilon zeta eta theta iota kappa lambda.";
const docs: GraphDocument[] = [
  { id: "src-01", model_name: "FuenteDoc", path: "s.md", payload: { title: "Acta", body: BODY } },
  { id: "src-02", model_name: "FuenteDoc", path: "s2.md", payload: { title: "Otra", body: "x" } },
  { id: "a-1", model_name: "AtomDoc", path: "a1", payload: { title: "Uno", source: "FuenteDoc:src-01", quote: "beta gamma", status: "confirmado" } },
  { id: "a-0", model_name: "AtomDoc", path: "a0", payload: { title: "Cero", source: "src-01", quote: "Alfa" } },
  { id: "a-empty", model_name: "AtomDoc", path: "ae", payload: { title: "Huérfano", source: "", quote: "iota" } },
  { id: "a-other", model_name: "AtomDoc", path: "ao", payload: { title: "Ajeno", source: "FuenteDoc:src-02", quote: "x" } },
];

function fakeClient(rank: unknown): SldbClient {
  return {
    document: vi.fn().mockResolvedValue({ id: "src-01", model_name: "FuenteDoc", path: "s.md", payload: { title: "Acta", body: BODY } }),
    getEdges: vi.fn().mockResolvedValue([]),
    rank: vi.fn().mockResolvedValue(rank),
    createDocument: vi.fn().mockResolvedValue({ ok: true, id: "x", version: "1" }),
  } as unknown as SldbClient;
}

/** Punto DOM del carácter `offset` del body, ignorando los widgets `<sup>` de las decoraciones. */
function domPoint(pm: Element, offset: number): { node: Text; offset: number } {
  const walker = document.createTreeWalker(pm, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) =>
      n.parentElement?.closest(".wb-pm-anchor-sup") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
  });
  let rest = offset;
  for (let n = walker.nextNode() as Text | null; n; n = walker.nextNode() as Text | null) {
    if (rest <= n.data.length) return { node: n, offset: rest };
    rest -= n.data.length;
  }
  throw new Error(`offset ${offset} fuera del body`);
}

function mount(client: SldbClient) {
  return render(
    <SourceAnchoringView client={client} documents={docs} activeSourceId="src-01" onSelectSource={vi.fn()} onDocumentsMutated={vi.fn()} onNavigateToDoc={vi.fn()} />,
  );
}

describe("SourceAnchoringView", () => {
  it("filtra átomos por fuente y excluye los de source vacío", async () => {
    mount(fakeClient({ status: "ok", hits: [] }));
    await waitFor(() => expect(screen.getByTestId("anchor-atom-a-1")).toBeTruthy());
    expect(screen.getByTestId("anchor-atom-a-0")).toBeTruthy();
    expect(screen.queryByTestId("anchor-atom-a-empty")).toBeNull();
    expect(screen.queryByTestId("anchor-atom-a-other")).toBeNull();
    expect(atomBelongsToSource(docs[4]!, "src-01")).toBe(false);
  });

  it("calcula cobertura uniendo rangos solapados", () => {
    expect(computeCoverage([{ start: 0, end: 10 }, { start: 5, end: 20 }, { start: -1, end: -1 }], 100)).toEqual({ coveredChars: 20, totalChars: 100, pct: 20 });
    expect(computeCoverage([], 0).pct).toBe(0);
  });

  it("muestra cobertura real en el panel", async () => {
    mount(fakeClient({ status: "ok", hits: [] }));
    await waitFor(() => expect(screen.getByTestId("coverage-pct").textContent).toContain("14"));
  });

  for (const result of [
    { status: "not_indexed" },
    { status: "unavailable", reason: "sin embedder" },
  ]) {
    it(`no dice "Nuevo en el store" con ${result.status}`, async () => {
      const client = fakeClient(result);
      mount(client);
      await waitFor(() => expect(screen.getByTestId("anchor-atom-a-1")).toBeTruthy());
      const viewer = screen.getByTestId("prosemirror-source-viewer");
      // El editor se recrea cuando llega el body de la fuente: esperar a ese editor.
      await waitFor(() => expect(viewer.querySelector(".ProseMirror")?.textContent).toContain("epsilon"));
      const pm = viewer.querySelector(".ProseMirror")!;
      const range = document.createRange();
      range.setStart(pm, 0);
      range.setEnd(pm, pm.childNodes.length);
      const sel = document.getSelection()!;
      await act(async () => {
        sel.removeAllRanges();
        sel.addRange(range);
        document.dispatchEvent(new Event("selectionchange"));
      });
      await waitFor(() => expect(screen.getByTestId("anchor-popover")).toBeTruthy());
      await waitFor(() => expect(client.rank).toHaveBeenCalled(), { timeout: 2000 });
      await waitFor(() => expect(screen.getByTestId("anchor-rank-status").textContent).toMatch(/indexado|no disponible/));
      expect(document.body.textContent).not.toContain("Nuevo en el store");
      fireEvent.keyDown(document, { key: "Escape" });
      await waitFor(() => expect(screen.queryByTestId("anchor-popover")).toBeNull());
    });
  }
  it("decora exactamente body[start:end], sin correrse un carácter", async () => {
    mount(fakeClient({ status: "ok", hits: [] }));
    const viewer = screen.getByTestId("prosemirror-source-viewer");
    await waitFor(() => expect(viewer.querySelector(".ProseMirror")?.textContent).toContain("epsilon"));
    const spans = [...viewer.querySelectorAll(".wb-pm-anchored-span")].map((n) => n.textContent);
    expect(spans).toEqual(["Alfa", "beta gamma"]);
    const sups = [...viewer.querySelectorAll(".wb-pm-anchor-sup")].map((n) => n.textContent);
    expect(sups).toEqual(["[a-0 · 0:4]", "[a-1 · 5:15]"]);
  });

  it("la selección de ProseMirror es exactamente sourceText.slice(start, end)", async () => {
    mount(fakeClient({ status: "ok", hits: [] }));
    const viewer = screen.getByTestId("prosemirror-source-viewer");
    await waitFor(() => expect(viewer.querySelector(".ProseMirror")?.textContent).toContain("epsilon"));
    const pm = viewer.querySelector(".ProseMirror")!;
    const start = BODY.indexOf("epsilon");
    const end = start + "epsilon zeta".length;
    const a = domPoint(pm, start);
    const b = domPoint(pm, end);
    const range = document.createRange();
    range.setStart(a.node, a.offset);
    range.setEnd(b.node, b.offset);
    await act(async () => {
      const sel = document.getSelection()!;
      sel.removeAllRanges();
      sel.addRange(range);
      document.dispatchEvent(new Event("selectionchange"));
    });
    const popover = await screen.findByTestId("anchor-popover");
    expect(popover.textContent).toContain(`body[${start}:${end}]`);
    expect(BODY.slice(start, end)).toBe("epsilon zeta");
    const symbol = popover.querySelector("input") as HTMLInputElement;
    expect(symbol.value).toMatch(/epsilon/);
    expect(symbol.value).not.toMatch(/delta|eta-theta/);
  });

  it("downstream incluye consumidores entrantes y salientes, sin la FuenteDoc de origen", () => {
    const edge = (id: string, source: string, target: string): Edge => ({
      id, source, target, type: "ref", origin: "payload", relationDoc: null,
    });
    const edges = [
      edge("in", "InformeDoc:rep-01", "AtomDoc:a-1"),
      edge("node", "SpecNodeDoc:n1", "AtomDoc:a-1"),
      edge("src", "AtomDoc:a-1", "FuenteDoc:src-01"),
      edge("out", "AtomDoc:a-1", "TaskDoc:t-9"),
      edge("ajena", "InformeDoc:rep-01", "AtomDoc:a-2"),
    ];
    expect(downstreamLinks(edges, "a-1").map((e) => e.id)).toEqual(["in", "node", "out"]);
  });

  it("no muestra un chip de tipo si la FuenteDoc no declara kind ni type", async () => {
    mount(fakeClient({ status: "ok", hits: [] }));
    await waitFor(() => expect(screen.getByTestId("prosemirror-source-viewer").textContent).toContain("epsilon"));
    expect(screen.queryByText("Protocolo Vinculante")).toBeNull();
  });
});

describe("SourceAnchoringView · offsets declarados por el AtomDoc", () => {
  it("storedOffsets acepta start_offset/end_offset o start/end enteros dentro del texto", () => {
    expect(storedOffsets({ start_offset: 5, end_offset: 15 }, 64)).toEqual({ start: 5, end: 15 });
    expect(storedOffsets({ start: 0, end: 4 }, 64)).toEqual({ start: 0, end: 4 });
    expect(storedOffsets({ start_offset: 2, end_offset: 9, start: 30, end: 40 }, 64)).toEqual({ start: 2, end: 9 });
  });

  it("storedOffsets rechaza offsets ausentes, no enteros, invertidos o fuera del texto", () => {
    expect(storedOffsets({}, 64)).toBeNull();
    expect(storedOffsets({ start_offset: "5", end_offset: "9" }, 64)).toBeNull();
    expect(storedOffsets({ start_offset: 1.5, end_offset: 9 }, 64)).toBeNull();
    expect(storedOffsets({ start_offset: 9, end_offset: 9 }, 64)).toBeNull();
    expect(storedOffsets({ start_offset: -1, end_offset: 9 }, 64)).toBeNull();
    expect(storedOffsets({ start_offset: 60, end_offset: 65 }, 64)).toBeNull();
  });

  it("usa los offsets guardados antes que indexOf(quote) y cae al indexOf si no son válidos", async () => {
    // a-off: tramo guardado coherente con su cita; a-bad: offsets fuera del texto → indexOf;
    // a-moved: offsets válidos aunque la cita ya no esté en la fuente → se respetan.
    const withOffsets: GraphDocument[] = [
      docs[0]!,
      { id: "a-off", model_name: "AtomDoc", path: "ao", payload: { title: "Con offsets", source: "src-01", quote: "gamma", start_offset: 10, end_offset: 15 } },
      { id: "a-bad", model_name: "AtomDoc", path: "ab", payload: { title: "Offsets inválidos", source: "src-01", quote: "delta", start_offset: 500, end_offset: 900 } },
      { id: "a-moved", model_name: "AtomDoc", path: "am", payload: { title: "Fuente cambió", source: "src-01", quote: "omega", start: 0, end: 4 } },
    ];
    render(
      <SourceAnchoringView
        client={fakeClient({ status: "ok", hits: [] })}
        documents={withOffsets}
        activeSourceId="src-01"
        onSelectSource={vi.fn()}
        onDocumentsMutated={vi.fn()}
        onNavigateToDoc={vi.fn()}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("anchor-atom-a-off").textContent).toContain("body[10:15]"));
    expect(screen.getByTestId("anchor-atom-a-bad").textContent).toContain(`body[${BODY.indexOf("delta")}:${BODY.indexOf("delta") + 5}]`);
    expect(screen.getByTestId("anchor-atom-a-moved").textContent).toContain("body[0:4]");
  });
});

// ---------- store real (desk de sldb): sin FuenteDoc; AtomDoc de deskops con `provenance` ----------

const ARCH_BODY = "El índice de docstrings enlaza cada símbolo con su contrato.";
const realDesk: GraphDocument[] = [
  { id: "packaging", model_name: "PackagingDoc", path: "docs/packaging.md", payload: { title: "Packaging", body: "Instrucciones." } },
  { id: "req-kg", model_name: "RequestDoc", path: "docs/requests/kg.md", payload: { title: "Request KG", body: "## Context" } },
  { id: "arch-docstrings", model_name: "ArchitectureNarrativeDoc", path: "docs/architecture/code-docstring-indexing.spec.md", payload: { title: "Docstring Indexing", body: ARCH_BODY } },
  { id: "sym-1", model_name: "PythonSymbolDoc", path: "src/x.py", payload: { title: "x" } },
  { id: "readme", model_name: "StoreReadmeDoc", path: "README.md", payload: { title: "Readme" } },
  {
    id: "atom-docstrings",
    model_name: "AtomDoc",
    path: "desk/atoms/atom-docstrings.md",
    payload: { title: "Los docstrings son contrato", answer: "Cada símbolo público declara su contrato.", five_wh_one_plus: "what", provenance: "docs/architecture/code-docstring-indexing.spec.md" },
  },
  { id: "atom-address-space", model_name: "AtomicDocumentDoc", path: "docs/atoms/address-space.atom.md", payload: { title: "Address Space", what_it_is: "Cómo se direcciona cada campo." } },
  { id: "atom-sin-origen", model_name: "AtomDoc", path: "desk/atoms/b.md", payload: { title: "Sin origen", answer: "x" } },
];

describe("SourceAnchoringView · store real", () => {
  it("isAnchorableSource: fuentes nombradas del demo o documentos no-átomo con prosa", () => {
    const by = (id: string) => [...realDesk, ...docs].find((d) => d.id === id)!;
    expect(isAnchorableSource(by("src-01"))).toBe(true);
    expect(isAnchorableSource(by("arch-docstrings"))).toBe(true);
    expect(isAnchorableSource(by("req-kg"))).toBe(true);
    expect(isAnchorableSource(by("sym-1"))).toBe(false);
    expect(isAnchorableSource(by("readme"))).toBe(false);
    expect(isAnchorableSource(by("atom-docstrings"))).toBe(false);
  });

  it("atomBelongsToSource reconoce `provenance` por ruta (con ./ o #ancla) además de `source` por id", () => {
    const atom = realDesk.find((d) => d.id === "atom-docstrings")!;
    const path = "docs/architecture/code-docstring-indexing.spec.md";
    expect(atomBelongsToSource(atom, "arch-docstrings", path)).toBe(true);
    expect(atomBelongsToSource(atom, "arch-docstrings", `./${path}`)).toBe(true);
    expect(atomBelongsToSource({ ...atom, payload: { provenance: `${path}#contrato` } }, "arch-docstrings", path)).toBe(true);
    expect(atomBelongsToSource(atom, "req-kg", "docs/requests/kg.md")).toBe(false);
    expect(atomBelongsToSource(atom, "arch-docstrings")).toBe(false);
    // El demo sigue igual: `source: FuenteDoc:src-01` por id.
    expect(atomBelongsToSource(docs[2]!, "src-01")).toBe(true);
  });

  it("rankSources: nombradas primero, luego las más citadas, sin símbolos ni átomos", () => {
    expect(rankSources(realDesk).map((d) => d.id)).toEqual(["arch-docstrings", "packaging", "req-kg"]);
    expect(rankSources([...realDesk, docs[0]!]).map((d) => d.id)[0]).toBe("src-01");
  });

  it("downstreamLinks descarta la arista de vuelta a la fuente seleccionada aunque no sea FuenteDoc", () => {
    const edges = [
      { id: "1", source: "AtomDoc:atom-docstrings", target: "ArchitectureNarrativeDoc:arch-docstrings", type: "provenance" },
      { id: "2", source: "TaskDocsDoc:task-1", target: "AtomDoc:atom-docstrings", type: "atoms" },
    ] as Edge[];
    expect(downstreamLinks(edges, "atom-docstrings", "arch-docstrings").map((e) => e.id)).toEqual(["2"]);
    expect(downstreamLinks(edges, "atom-docstrings").map((e) => e.id)).toEqual(["1", "2"]);
  });

  it("con el desk real lista fuentes con prosa y ancla el AtomDoc por provenance", async () => {
    const byId = new Map(realDesk.map((d) => [d.id, d]));
    const client = {
      document: vi.fn(async (id: string) => byId.get(id)),
      getEdges: vi.fn().mockResolvedValue([]),
      rank: vi.fn().mockResolvedValue({ status: "ok", hits: [] }),
      createDocument: vi.fn(),
    } as unknown as SldbClient;
    render(
      <SourceAnchoringView client={client} documents={realDesk} activeSourceId={null} onSelectSource={vi.fn()} onDocumentsMutated={vi.fn()} onNavigateToDoc={vi.fn()} />,
    );
    const select = (await screen.findByLabelText("FuenteDoc")) as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toEqual(["arch-docstrings", "packaging", "req-kg"]);
    expect(client.document).toHaveBeenCalledWith("arch-docstrings");
    const atom = await screen.findByTestId("anchor-atom-atom-docstrings");
    expect(atom.textContent).toContain("Los docstrings son contrato");
    // Sin `quote` no hay cita que se haya alterado: el chip lo dice tal cual.
    expect(atom.textContent).toContain("sin cita");
    expect(atom.textContent).not.toContain("cita alterada");
    expect(screen.queryByTestId("anchor-atom-atom-address-space")).toBeNull();
    expect(screen.queryByTestId("anchor-atom-atom-sin-origen")).toBeNull();
  });
});
