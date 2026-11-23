/**
 * La lente Lectura como wiki de configuración del tutor: índice con la configuración primero y el
 * resto de la base plegado y en solo lectura, títulos legibles y el rechazo de un guardado junto al
 * campo que falló. Las formas (template, rutas, semánticas) son las de la KB `kbs/apos`.
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

const agentPayload = {
  id: "agent-tutor-apos",
  title: "Tutor APOS",
  role: "tutor",
  projection: "tutor",
  on_failure: "closed",
  policies: ["deny_if_no_context"],
  summary: "Tutor de la teoría APOS.",
  framing: "Eres un tutor experto en APOS.",
  instructions: "Responde en español usando SOLO la información incluida abajo.",
};
const atomPayload = { id: "atom-accion", title: "La Acción es una estructura mental", answer: "APOS incluye la Acción." };

const pages: Record<string, DocumentSegments> = {
  "agent-tutor-apos": {
    id: "agent-tutor-apos",
    doc: "agent-tutor-apos",
    model: "AgentDoc",
    path: "agent/agent-tutor-apos.md",
    text: "",
    canonical: true,
    payload: agentPayload,
    segments: segmentsOf([
      "---\ntitle: ",
      ["title", "Tutor APOS"],
      "\nrole: ",
      ["role", "tutor"],
      "\non_failure: ",
      ["on_failure", "closed", { kind: "enum" }],
      "\nsummary: ",
      ["summary", "Tutor de la teoría APOS."],
      "\n---\n\n# ",
      ["title", "Tutor APOS", { marker: "render", editable: false }],
      "\n\n## Framing\n\n",
      ["framing", "Eres un tutor experto en APOS.", { display: "block" }],
      "\n\n## Instructions\n\n",
      ["instructions", "Responde en español usando SOLO la información incluida abajo.", { display: "block" }],
    ]),
  },
  "atom-accion": {
    id: "atom-accion",
    doc: "atom-accion",
    model: "KnowledgeAtom",
    path: "knowledge/core-structures/action/atom-accion.md",
    text: "",
    canonical: true,
    payload: atomPayload,
    segments: segmentsOf([
      "---\ntitle: ",
      ["title", "La Acción es una estructura mental"],
      "\n---\n\n# ",
      ["title", "La Acción es una estructura mental", { marker: "render", editable: false }],
      "\n\n## Respuesta\n\n",
      ["answer", "APOS incluye la Acción.", { display: "block" }],
    ]),
  },
};

const documents: GraphDocument[] = [
  { id: "child_of", model_name: "RelationTypeDoc", path: "kgdb/relation_types/child_of.md", payload: { name: "child_of" } },
  { id: "atom-accion", model_name: "KnowledgeAtom", path: "knowledge/core-structures/action/atom-accion.md", payload: atomPayload },
  { id: "atom-proceso", model_name: "KnowledgeAtom", path: "knowledge/core-structures/process/atom-proceso.md", payload: { title: "El Proceso" } },
  { id: "branch-apos", model_name: "BranchNode", path: "taxonomy/branch-apos.md", payload: { title: "APOS" } },
  { id: "agent-tutor-apos", model_name: "AgentDoc", path: "agent/agent-tutor-apos.md", payload: agentPayload },
];

const catalog = (name: string, type: string): ModelCatalogEntry => ({
  name,
  model_ref: `kb_models:${name}`,
  path: "kb_models.py",
  version: 1,
  canonical: false,
  family: null,
  semantics: [`type.${type}`],
  documents: 0,
});

const models = [
  catalog("AgentDoc", "governance.agent"),
  catalog("BranchNode", "knowledge.branch"),
  catalog("KnowledgeAtom", "knowledge.atom"),
  catalog("RelationTypeDoc", "relation.type"),
];

const titled = (id: string): SchemaResponse["models"][number] => ({ id, model_ref: `p:${id}`, template: "---\ntitle: ⸢rev•title⸥\n---\n\n# ⸢render•title⸥", fields: [{ name: "title", kind: "string", required: true }] });
const schema: SchemaResponse = { models: [titled("AgentDoc"), titled("BranchNode"), titled("KnowledgeAtom"), { ...titled("RelationTypeDoc"), template: "# ⸢render•name⸥" }] };

/** Como `sldb serve`: la autoridad es del modelo. Solo la configuración es `authored`. */
const authorityOf = (name: string) => (name === "AgentDoc" ? "authored" : "generated");

const RECHAZO =
  "agent-tutor-apos: 1 validation error for AgentDoc\non_failure\n  Input should be 'open' or 'closed' [type=literal_error, input_value='abierto', input_type=str]";

function mount(over: { docId?: string; lens?: WorkbenchLens; docs?: GraphDocument[]; saveError?: Error } = {}) {
  const fake = {
    schema: vi.fn(async () => schema),
    segments: vi.fn(async (id: string) => {
      const page = pages[id];
      if (!page) throw new Error(`sin segmentos: ${id}`);
      return page;
    }),
    describeModel: vi.fn(async (name: string) => ({ name, model_ref: `kb_models:${name}`, authority: authorityOf(name) }) as unknown as ModelDescription),
    getEdges: vi.fn(async () => []),
    document: vi.fn(),
    save: vi.fn(async (_changes: unknown[]) => {
      if (over.saveError) throw over.saveError;
      return { ok: true };
    }),
  };
  const props = {
    docId: over.docId ?? "agent-tutor-apos",
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
  await index().findByRole("button", { name: "Tutor APOS" });
}

// ---------- 1. índice ----------

describe("Wiki · índice del panel izquierdo", () => {
  it("lectura: la configuración del tutor primero y abierta; el resto de la base, plegado y en solo lectura", async () => {
    mount();
    await ready("Tutor APOS");
    expect(screen.queryByTestId("topology-mindmap")).toBeNull();
    expect(index().getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual(["Configuración del tutor", "La base · solo lectura"]);
    expect(within(screen.getByTestId("wiki-group-agent")).getAllByRole("button").map((b) => b.textContent)).toEqual(["Tutor APOS"]);
    expect(index().getByRole("button", { current: "page" }).textContent).toBe("Tutor APOS");
    const base = within(screen.getByTestId("wiki-generated"));
    expect(Array.from(screen.getByTestId("wiki-generated").querySelectorAll("summary")).map((s) => s.textContent)).toEqual([
      "Ramas 1",
      "Átomos de conocimiento 2",
      "Tipos de relación 1",
    ]);
    expect((screen.getByTestId("wiki-group-knowledge") as HTMLDetailsElement).open).toBe(false);
    expect(base.getByText(/Se genera desde los átomos fuente/)).toBeTruthy();
  });

  it("aquí no se crean ni se quitan páginas", async () => {
    mount();
    await ready("Tutor APOS");
    expect(screen.queryByRole("button", { name: /Agregar/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Quitar/ })).toBeNull();
  });

  it("elegir una página del índice navega a ella; el grupo de la página abierta se despliega", async () => {
    const { props } = mount({ docId: "atom-accion" });
    await ready("La Acción es una estructura mental");
    expect((screen.getByTestId("wiki-group-knowledge") as HTMLDetailsElement).open).toBe(true);
    fireEvent.click(index().getByRole("button", { name: "El Proceso" }));
    expect(props.onSelectDoc).toHaveBeenCalledWith("atom-proceso");
  });

  it("fierros: se conserva el mapa y no hay índice", async () => {
    mount({ lens: "fierros" });
    await screen.findByTestId("topology-mindmap");
    expect(screen.queryByTestId("wiki-index")).toBeNull();
  });
});

// ---------- 2. qué se edita y qué no ----------

describe("Wiki · configuración editable, base en solo lectura", () => {
  it("la página del tutor se edita en el lugar: el encuadre se guarda con POST /save action=update y el payload leído como expected", async () => {
    const { fake, props } = mount();
    await ready("Tutor APOS");
    expect(screen.queryByTestId("prosa-solo-lectura")).toBeNull();
    expect(screen.getByLabelText("Rol")).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Eres un tutor experto en APOS." }));
    const area = screen.getByRole("textbox", { name: "" });
    fireEvent.change(area, { target: { value: "Eres un tutor paciente." } });
    fireEvent.blur(area);
    await waitFor(() => expect(fake.save).toHaveBeenCalled());
    const [change] = fake.save.mock.calls[0]![0] as { id: string; action: string; model: string; payload: Record<string, unknown>; expected: unknown }[];
    expect(change).toMatchObject({ id: "agent-tutor-apos", action: "update", model: "AgentDoc", expected: agentPayload });
    expect(change!.payload.framing).toBe("Eres un tutor paciente.");
    await waitFor(() => expect(props.onDocumentsMutated).toHaveBeenCalled()); // el índice relee el store
  });

  it("un átomo se lee, dice por qué no se edita y no ofrece controles", async () => {
    const { fake } = mount({ docId: "atom-accion" });
    await ready("La Acción es una estructura mental");
    expect((await screen.findByTestId("prosa-solo-lectura")).textContent).toMatch(/se genera desde los átomos fuente/);
    expect(screen.getByText("APOS incluye la Acción.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "APOS incluye la Acción." })).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(fake.save).not.toHaveBeenCalled();
  });
});

// ---------- 3. se lee como la wiki ----------

describe("Wiki · títulos y metadatos", () => {
  it("lectura: sin metadatos de sldb", async () => {
    mount();
    await ready("Tutor APOS");
    expect(screen.queryByText(/AgentDoc/)).toBeNull();
    expect(screen.queryByText(/path:/)).toBeNull();
  });

  it("fierros: la línea de modelo y path sigue ahí", async () => {
    mount({ lens: "fierros" });
    expect(await screen.findByText(/AgentDoc ·/)).toBeTruthy();
    expect(screen.getByText(/path: agent\/agent-tutor-apos\.md/)).toBeTruthy();
  });
});

// ---------- 4. errores de guardado ----------

describe("Wiki · rechazo de un guardado", () => {
  it("queda en la fila del campo que falló, legible y con el texto del servidor sin tocar", async () => {
    mount({ saveError: new SldbHttpError(RECHAZO, 422, null) });
    await ready("Tutor APOS");
    const campo = await screen.findByLabelText("Rol");
    fireEvent.change(campo, { target: { value: "otro" } });
    fireEvent.blur(campo);
    const alert = await screen.findByTestId("prosa-save-error");
    expect(alert.getAttribute("role")).toBe("alert");
    expect(within(alert).getByText("No se guardó este cambio")).toBeTruthy();
    expect(alert.querySelector(".wb-aviso__mensaje")!.textContent).toBe(RECHAZO);
    expect(alert.closest("dd")).toBe(campo.closest("dd"));
    fireEvent.click(within(alert).getByRole("button", { name: "Cerrar el aviso" }));
    expect(screen.queryByTestId("prosa-save-error")).toBeNull();
  });
});
