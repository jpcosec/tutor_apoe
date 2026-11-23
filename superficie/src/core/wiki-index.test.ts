import { describe, expect, it } from "vitest";
import type { GraphDocument, ModelCatalogEntry, SchemaModel } from "./contract";
import {
  allowsMany,
  buildWikiIndex,
  businessName,
  humanize,
  newPageId,
  newPagePayload,
  pageLabel,
  planNewPage,
  slug,
  templateTitle,
  templateTraits,
  typeLabel,
} from "./wiki-index";

const doc = (id: string, model_name: string, path: string, payload: Record<string, unknown> = {}): GraphDocument => ({
  id,
  model_name,
  path,
  payload,
});

const model = (name: string, type: string): ModelCatalogEntry => ({
  name,
  model_ref: `paginas:${name}`,
  path: "paginas.py",
  version: 1,
  canonical: false,
  family: null,
  semantics: ["representation.markdown", `type.${type}`],
  documents: 0,
});

// Los templates y semánticas son los que entrega el store de la peluquería (`GET /schema`, `GET /models`).
const schema: SchemaModel[] = [
  {
    id: "NegocioDoc",
    model_ref: "p:NegocioDoc",
    template: "---\nnombre: ⸢rev•nombre⸥\n---\n\n# ⸢render•nombre⸥\n\n⸢rev,markdown•descripcion⸥",
    fields: [
      { name: "nombre", kind: "string", required: true },
      { name: "rubro", kind: "string", required: true },
      { name: "lema", kind: "string", required: false, default: "" },
      { name: "descripcion", kind: "string", required: true },
    ],
  },
  {
    id: "HorarioDoc",
    model_ref: "p:HorarioDoc",
    template: "---\ncerrado: ⸢rev,list•cerrado⸥\n---\n\n# Horario\n\n## Atención\n\n```yaml\n⸢rev,dict•atencion⸥\n```",
    fields: [
      { name: "cerrado", kind: "list", required: false },
      { name: "atencion", kind: "unknown", required: true },
    ],
  },
  {
    id: "ServicioDoc",
    model_ref: "p:ServicioDoc",
    template: "---\nnombre: ⸢rev•nombre⸥\nprecio: ⸢rev•precio⸥\n---\n\n# ⸢render•nombre⸥\n\n⸢rev,markdown•descripcion⸥",
    fields: [
      { name: "nombre", kind: "string", required: true },
      { name: "duracion_min", kind: "integer", required: true },
      { name: "precio", kind: "unknown", required: true },
      { name: "visible", kind: "boolean", required: false, default: true },
      { name: "descripcion", kind: "string", required: true },
    ],
  },
  { id: "ProfesionalDoc", model_ref: "p:ProfesionalDoc", template: "# ⸢render•nombre⸥", fields: [{ name: "nombre", kind: "string", required: true }] },
  { id: "AsistenteDoc", model_ref: "p:AsistenteDoc", template: "# Asistente ⸢render•nombre⸥", fields: [{ name: "nombre", kind: "string", required: true }] },
];

const models = [
  model("AsistenteDoc", "paquete.asistente"),
  model("HorarioDoc", "negocio.horario"),
  model("NegocioDoc", "negocio.informacion-general"),
  model("ProfesionalDoc", "paquete.personal.profesional"),
  model("ServicioDoc", "paquete.catalogo.servicio"),
];

const documents = [
  doc("negocio", "NegocioDoc", "negocio.md", { nombre: "Peluquería Rayén" }),
  doc("horario", "HorarioDoc", "horario.md", {}),
  doc("balayage", "ServicioDoc", "servicios/balayage.md", { nombre: "Balayage" }),
  doc("corte-de-pelo-hombre", "ServicioDoc", "servicios/corte-de-pelo-hombre.md", { nombre: "Corte de pelo hombre" }),
  doc("rayen-soto", "ProfesionalDoc", "equipo/rayen-soto.md", { nombre: "Rayén Soto" }),
  doc("asistente", "AsistenteDoc", "asistente.md", { nombre: "Rayo" }),
];

describe("wiki-index · rótulos", () => {
  it("humaniza ids, tipos e identificadores", () => {
    expect(humanize("identidad-visual")).toBe("Identidad visual");
    expect(typeLabel("IdentidadVisualDoc")).toBe("Identidad visual");
    expect(typeLabel("ServicioDoc")).toBe("Servicio");
    expect(slug("  Peinado de Fiesta (niñas) ")).toBe("peinado-de-fiesta-ninas");
  });

  it("lee el título y los rasgos del template", () => {
    expect(templateTitle(schema[1]!.template)).toEqual({ literal: "Horario", field: null });
    expect(templateTitle(schema[0]!.template)).toEqual({ literal: "", field: "nombre" });
    expect(templateTitle(schema[4]!.template)).toEqual({ literal: "Asistente", field: "nombre" });
    expect(templateTitle(undefined)).toBeNull();
    expect(templateTraits(schema[1]!.template).get("atencion")).toEqual(["rev", "dict"]);
  });

  it("una página única se llama como su template o su tipo; una de varias, por su nombre", () => {
    expect(pageLabel(documents[1]!, false, schema[1])).toBe("Horario");
    expect(pageLabel(documents[0]!, false, schema[0])).toBe("Negocio");
    expect(pageLabel(documents[5]!, false, schema[4])).toBe("Asistente");
    expect(pageLabel(documents[2]!, true, schema[2])).toBe("Balayage");
    expect(pageLabel(doc("sin-nombre", "ServicioDoc", "servicios/sin-nombre.md"), true, schema[2])).toBe("Sin nombre");
    // Un store cualquiera: sin template, el `title` del documento.
    expect(pageLabel(doc("informe-1", "InformeDoc", "informe-1.md", { title: "Informe renal" }), false)).toBe("Informe renal");
  });

  it("el nombre del negocio sale de su página NegocioDoc", () => {
    expect(businessName(documents)).toBe("Peluquería Rayén");
    expect(businessName(documents.slice(1))).toBeNull();
  });
});

describe("wiki-index · grupos", () => {
  it("agrupa por carpeta o por semántica, en el orden del schema, sin nada escrito a mano", () => {
    const groups = buildWikiIndex(documents, models, schema);
    expect(groups.map((g) => g.label)).toEqual(["Negocio", "Servicios", "Equipo", "Asistente"]);
    expect(groups[0]!.pages.map((p) => p.label)).toEqual(["Negocio", "Horario"]);
    expect(groups[1]!.pages.map((p) => p.label)).toEqual(["Balayage", "Corte de pelo hombre"]);
  });

  it("solo los tipos con varias páginas ofrecen agregar otra", () => {
    const groups = buildWikiIndex(documents, models, schema);
    expect(groups[0]!.creatable).toEqual([]);
    expect(groups[1]!.creatable).toEqual([{ model: "ServicioDoc", label: "servicio" }]);
    expect(groups[2]!.creatable).toEqual([{ model: "ProfesionalDoc", label: "profesional" }]);
    expect(groups[3]!.creatable).toEqual([]);
    expect(allowsMany([documents[1]!])).toBe(false);
    expect(allowsMany([documents[4]!])).toBe(true);
  });

  it("una wiki vacía ofrece la primera página de cada tipo", () => {
    const groups = buildWikiIndex([], models, schema);
    expect(groups.every((g) => g.pages.length === 0)).toBe(true);
    expect(groups.flatMap((g) => g.creatable.map((c) => c.model))).toEqual([
      "NegocioDoc",
      "HorarioDoc",
      "ServicioDoc",
      "ProfesionalDoc",
      "AsistenteDoc",
    ]);
    expect(groups[0]!.label).toBe("Negocio");
    expect(groups[0]!.creatable.map((c) => c.label)).toEqual(["negocio", "horario"]);
  });

  it("sin schema ni catálogo no falla: agrupa por el tipo del documento", () => {
    const groups = buildWikiIndex([doc("informe-1", "InformeDoc", "informe-1.md", { title: "Informe renal" })], []);
    expect(groups).toEqual([
      { key: "Informe", label: "Informe", pages: [{ id: "informe-1", model: "InformeDoc", label: "Informe renal" }], creatable: [] },
    ]);
  });
});

describe("wiki-index · página nueva", () => {
  it("pide los obligatorios; los que tienen estructura parten vacíos", () => {
    const servicio = planNewPage(schema[2]);
    expect(servicio.fields.map((f) => f.field.name)).toEqual(["nombre", "duracion_min", "precio", "descripcion"]);
    expect(servicio.fields.find((f) => f.field.name === "descripcion")!.long).toBe(true);
    expect(servicio.nameField).toBe("nombre");
    const horario = planNewPage(schema[1]);
    expect(horario.fields).toEqual([]);
    expect(horario.preset).toEqual({ atencion: {} });
    expect(horario.nameField).toBeNull();
  });

  it("arma el payload con el tipo de cada campo y sin validar: lo vacío no viaja", () => {
    const plan = planNewPage(schema[2]);
    expect(newPagePayload(plan, { nombre: " Corte ", duracion_min: "30", precio: "a cotizar", descripcion: "" })).toEqual({
      nombre: "Corte",
      duracion_min: 30,
      precio: "a cotizar",
    });
    expect(newPagePayload(plan, { precio: "14000", duracion_min: "media hora" })).toEqual({ precio: 14000, duracion_min: "media hora" });
  });

  it("el id sale del nombre; sin campo de nombre, o con el nombre en blanco, del tipo", () => {
    expect(newPageId("ServicioDoc", planNewPage(schema[2]), { nombre: "Corte de niña" })).toBe("corte-de-nina");
    expect(newPageId("ServicioDoc", planNewPage(schema[2]), {})).toBe("servicio");
    expect(newPageId("HorarioDoc", planNewPage(schema[1]), {})).toBe("horario");
  });
});
