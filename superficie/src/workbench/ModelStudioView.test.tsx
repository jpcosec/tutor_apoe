import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ModelStudioView } from "./ModelStudioView";
import {
  FIELD_TYPE_OPTIONS,
  deriveUmlNeighbours,
  promoteGate,
  reversibleBadge,
} from "./model-studio-logic";
import type { SldbClient } from "../core/client";
import type { ModelCatalogEntry, ModelDescription } from "../core/contract";

const entry = (name: string): ModelCatalogEntry => ({
  name, model_ref: `app.models.${name}`, path: "app/models.py", version: 1, canonical: true, family: null, semantics: [], documents: 1,
});

const desc = (name: string, over: Partial<ModelDescription> = {}): ModelDescription => ({
  ...entry(name),
  base_models: ["StructuredNLDoc"],
  fields: [{ name: "title", annotation: "str", description: "Título" }],
  documents: [],
  containment: {},
  references: [],
  compositions: {},
  semantics_map: {},
  authority: "authored",
  template: "# ⸢rev•title⸥\n",
  has_draft: true,
  draft_path: "app/.models_draft.py",
  ...over,
});

const INFORME = desc("InformeDoc", {
  fields: [
    { name: "title", annotation: "str", description: "Título" },
    { name: "criterios", annotation: "list[DocRef[AtomDoc]]", description: "" },
    { name: "diagrama_flujo", annotation: "DocRef[SpecDoc]", description: "" },
  ],
  references: ["diagrama_flujo"],
  compositions: { criterios: { source_field: "criterios", ref: "field", model: "AtomDoc" } },
});

function makeClient(report: Record<string, unknown> = { ok: true, valid: true, errors: [] }) {
  const details: Record<string, ModelDescription> = {
    InformeDoc: INFORME,
    AtomDoc: desc("AtomDoc", { fields: [{ name: "text", annotation: "str", description: "" }], template: "⸢rev•text⸥" }),
    SpecDoc: desc("SpecDoc"),
    DeskTask: desc("DeskTask", { model_ref: "deskops.models.DeskTask" }),
  };
  const fake = {
    modelsCatalog: vi.fn().mockResolvedValue([entry("InformeDoc"), entry("AtomDoc"), entry("SpecDoc")]),
    describeModel: vi.fn().mockImplementation(async (n: string) => details[n] ?? desc(n)),
    addModelField: vi.fn().mockResolvedValue({ ok: true }),
    removeModelField: vi.fn().mockResolvedValue({ ok: true }),
    editModelMetadata: vi.fn().mockResolvedValue({ ok: true }),
    editModelTemplate: vi.fn().mockResolvedValue({ ok: true }),
    validateModelDraft: vi.fn().mockResolvedValue(report),
    promoteModelDraft: vi.fn().mockResolvedValue({ ok: true }),
  };
  return { fake, client: fake as unknown as SldbClient };
}

async function mount(client: SldbClient, active = "InformeDoc", waitUml = true) {
  const onSelect = vi.fn();
  const utils = render(
    <ModelStudioView client={client} documents={[]} activeModelName={active} onSelectModel={onSelect} onModelsMutated={vi.fn()} />,
  );
  await screen.findByText("Contrato de Modelo:", { exact: false });
  if (waitUml) await screen.findByTestId("uml-box-AtomDoc");
  return { ...utils, onSelect };
}

const promote = () => screen.getByRole("button", { name: "Promover" }) as HTMLButtonElement;

describe("ModelStudioView · gate de promoción (bug #8)", () => {
  it("promover está deshabilitado antes de validar y se habilita tras un validate limpio", async () => {
    const { client, fake } = makeClient();
    await mount(client);
    expect(promote().disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Validar Draft" }));
    await waitFor(() => expect(promote().disabled).toBe(false));
    expect(fake.validateModelDraft).toHaveBeenCalledWith("InformeDoc");
    fireEvent.click(promote());
    await waitFor(() => expect(fake.promoteModelDraft).toHaveBeenCalledWith("InformeDoc", true));
  });

  it("una mutación posterior del draft lo vuelve a deshabilitar", async () => {
    const { client, fake } = makeClient();
    await mount(client);
    fireEvent.click(screen.getByRole("button", { name: "Validar Draft" }));
    await waitFor(() => expect(promote().disabled).toBe(false));
    fireEvent.change(screen.getByLabelText("nombre del campo"), { target: { value: "nuevo" } });
    fireEvent.click(screen.getByRole("button", { name: "+ Agregar campo" }));
    await waitFor(() => expect(fake.addModelField).toHaveBeenCalled());
    await waitFor(() => expect(promote().disabled).toBe(true));
    // y guardar plantilla también invalida
    fireEvent.click(screen.getByRole("button", { name: "Validar Draft" }));
    await waitFor(() => expect(promote().disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Guardar plantilla" }));
    await waitFor(() => expect(fake.editModelTemplate).toHaveBeenCalled());
    await waitFor(() => expect(promote().disabled).toBe(true));
  });

  it("un validate con errores mantiene promover deshabilitado y muestra los errores", async () => {
    const { client } = makeClient({ ok: true, valid: false, errors: ["campo x sin default"], warnings: ["aviso y"], backfill_required: ["x"], affected_documents: 3 });
    await mount(client);
    fireEvent.click(screen.getByRole("button", { name: "Validar Draft" }));
    expect(await screen.findByText("error: campo x sin default")).toBeTruthy();
    expect(screen.getByText("aviso: aviso y")).toBeTruthy();
    expect(promote().disabled).toBe(true);
  });

  it("cambiar de modelo invalida la validación", async () => {
    const { client } = makeClient();
    const onSelect = vi.fn();
    const props = { client, documents: [], onSelectModel: onSelect, onModelsMutated: vi.fn() };
    const { rerender } = render(<ModelStudioView {...props} activeModelName="InformeDoc" />);
    await screen.findByTestId("uml-box-AtomDoc");
    fireEvent.click(screen.getByRole("button", { name: "Validar Draft" }));
    await waitFor(() => expect(promote().disabled).toBe(false));
    rerender(<ModelStudioView {...props} activeModelName="AtomDoc" />);
    await waitFor(() => expect(screen.getByText("class AtomDoc", { selector: "span" })).toBeTruthy());
    await waitFor(() => expect(promote().disabled).toBe(true));
  });

  it("promoteGate: función pura", () => {
    const base = { editable: true, hasDraft: true, templateDirty: false, model: "M", rev: 2 };
    const ok = { model: "M", rev: 2, report: { ok: true, valid: true } };
    expect(promoteGate({ ...base, validation: ok }).enabled).toBe(true);
    expect(promoteGate({ ...base, validation: { ...ok, rev: 1 } }).enabled).toBe(false);
    expect(promoteGate({ ...base, validation: { ...ok, model: "N" } }).enabled).toBe(false);
    expect(promoteGate({ ...base, validation: { ...ok, report: { ok: true, valid: true, errors: ["e"] } } }).enabled).toBe(false);
    expect(promoteGate({ ...base, validation: ok, templateDirty: true }).enabled).toBe(false);
    expect(promoteGate({ ...base, validation: ok, editable: false, readOnlyReason: "solo lectura" }).reason).toBe("solo lectura");
  });
});

describe("ModelStudioView · formulario y UML", () => {
  it("ofrece exactamente los 8 tipos de campo", async () => {
    const { client } = makeClient();
    await mount(client);
    const select = screen.getByLabelText("tipo del campo");
    const values = within(select).getAllByRole("option").map((o) => (o as HTMLOptionElement).value);
    expect(values).toEqual(["str", "int", "float", "bool", "list[str]", "list[DocRef]", "DocRef[SpecDoc]", "DocRef[FuenteDoc]"]);
    expect(values).toEqual([...FIELD_TYPE_OPTIONS]);
  });

  it("dibuja vecinos UML de composiciones y referencias y navega al hacer click", async () => {
    const { client } = makeClient();
    const { onSelect } = await mount(client);
    expect(screen.getByTestId("uml-connector-composition-AtomDoc")).toBeTruthy();
    expect(screen.getByTestId("uml-connector-reference-SpecDoc")).toBeTruthy();
    expect(screen.getByText("extends StructuredNLDoc", { selector: ".ms-box--root *" })).toBeTruthy();
    expect(screen.getByText("«active root»")).toBeTruthy();
    expect(screen.getByText("3 registered classes")).toBeTruthy();
    fireEvent.click(screen.getByTestId("uml-box-SpecDoc"));
    expect(onSelect).toHaveBeenCalledWith("SpecDoc");
  });

  it("deriveUmlNeighbours: composición gana a referencia; ignora modelos fuera del catálogo", () => {
    const cat = [entry("InformeDoc"), entry("AtomDoc"), entry("SpecDoc")];
    const d = desc("InformeDoc", {
      fields: [
        { name: "criterios", annotation: "list[DocRef[AtomDoc]]", description: "" },
        { name: "fuente", annotation: "DocRef[FuenteDoc]", description: "" },
        { name: "atomo", annotation: "DocRef[AtomDoc]", description: "" },
      ],
      references: ["fuente", "atomo"],
      compositions: { criterios: { source_field: "criterios", ref: "field" } },
    });
    expect(deriveUmlNeighbours(d, cat)).toEqual([{ model: "AtomDoc", kind: "composition", field: "criterios" }]);
  });

  it("deriveUmlNeighbours: sin modelo en la anotación usa los prefijos Model: de los documentos reales", () => {
    const cat = [entry("SpecDoc"), entry("SpecNodeDoc"), entry("NotationDoc")];
    const d = desc("SpecDoc", {
      fields: [
        { name: "nodes", annotation: "list", description: "" },
        { name: "notation", annotation: "str", description: "" },
        { name: "summary", annotation: "str", description: "" },
      ],
      references: ["nodes", "notation"],
    });
    const docs = [
      { model_name: "SpecDoc", payload: { nodes: ["SpecNodeDoc:s.a", "SpecNodeDoc:s.b"], notation: "NotationDoc:activity", summary: "Foo: bar" } },
      { model_name: "SpecNodeDoc", payload: { nodes: ["GhostDoc:x"] } },
    ];
    expect(deriveUmlNeighbours(d, cat, docs)).toEqual([
      { model: "SpecNodeDoc", kind: "reference", field: "nodes" },
      { model: "NotationDoc", kind: "reference", field: "notation" },
    ]);
    expect(deriveUmlNeighbours(d, cat)).toEqual([]);
  });

  it("reversibleBadge sale del template y se omite si no hay marcador rev", () => {
    expect(reversibleBadge("x: ⸢rev,list•items⸥", "items")).toBe("⸢rev,list⸥");
    expect(reversibleBadge("x: ⸢render•items⸥", "items")).toBeNull();
    expect(reversibleBadge("sin marcas", "items")).toBeNull();
  });

  it("modelo de solo lectura: controles de mutación deshabilitados y razón visible", async () => {
    const { client, fake } = makeClient();
    fake.modelsCatalog.mockResolvedValue([{ ...entry("DeskTask"), model_ref: "deskops.models.DeskTask" }]);
    await mount(client, "DeskTask", false);
    expect(screen.getByTestId("readonly-notice").textContent).toMatch(/solo lectura/i);
    expect((screen.getByRole("button", { name: "+ Agregar campo" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText("__authority__") as HTMLSelectElement).disabled).toBe(true);
    expect(promote().disabled).toBe(true);
  });
});
