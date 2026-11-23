import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { DocumentSegments } from "../core/contract";
import type { SldbClient } from "../core/client";
import { FieldColors } from "../core/colors";
import { fieldRoots } from "../core/layout";
import { SldbProvider } from "./context";
import { DocumentSurface, type SurfaceEditing } from "./DocumentSurface";
import sap from "../core/__fixtures__/sap.segments.json";
import acuerdos from "../core/__fixtures__/acuerdos.segments.json";

const client = {} as SldbClient;

const schema = {
  models: [],
  errors: [],
  field: (_model: string, path: string) =>
    path === "status" ? { name: "status", kind: "enum" as const, required: true, enum: ["propuesta", "aceptada", "descartada"] } : undefined,
};

function mount(raw: unknown) {
  const data = raw as DocumentSegments;
  const commit = vi.fn();
  const editing: SurfaceEditing = { commit, pendingKey: null, error: null };
  render(
    <SldbProvider client={client}>
      <DocumentSurface
        segments={data.segments}
        target={{ doc: data.id, model: data.model }}
        model={data.model}
        payload={data.payload}
        colors={new FieldColors(fieldRoots(data.segments))}
        editing={editing}
        schema={schema}
      />
    </SldbProvider>,
  );
  return { commit, data };
}

describe("DocumentSurface", () => {
  it("edita un field inline por su dirección", () => {
    const { commit } = mount(sap);
    const title = screen.getByRole("textbox", { name: "title" });
    title.textContent = "Integración por archivos planos";
    fireEvent.blur(title);
    expect(commit).toHaveBeenCalledWith({ doc: "sap", model: "DecisionDoc" }, "title", "Integración por archivos planos");
  });

  it("el enum ofrece solo los valores del modelo y el texto del template no es editable", () => {
    const { commit } = mount(sap);
    const status = screen.getByRole("combobox", { name: "status" });
    fireEvent.change(status, { target: { value: "descartada" } });
    expect(commit).toHaveBeenCalledWith(expect.anything(), "status", "descartada");
    expect(screen.getByRole("heading", { name: "Contexto" }).querySelector("[contenteditable]")).toBeNull();
  });

  it("quita un ítem de lista reescribiendo la lista", () => {
    const { commit } = mount(sap);
    fireEvent.click(screen.getByRole("button", { name: "Quitar tags/0" }));
    expect(commit).toHaveBeenCalledWith(expect.anything(), "tags", ["system:sap"]);
  });

  it("un field de una pieza compuesta escribe en su documento de origen", () => {
    const { commit } = mount(acuerdos);
    const pieces = screen.getAllByRole("article");
    const title = within(pieces[1]!).getByRole("textbox", { name: "title" });
    title.textContent = "Semáforo a 2 días";
    fireEvent.blur(title);
    expect(commit).toHaveBeenCalledWith({ doc: "semaforo", model: "DecisionDoc" }, "title", "Semáforo a 2 días");
  });
});
