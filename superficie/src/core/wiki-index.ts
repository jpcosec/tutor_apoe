/**
 * El índice de la wiki: las páginas del store agrupadas por tipo, con nombres para personas.
 *
 * Nada se escribe a mano por negocio. Los grupos y rótulos salen de lo que el store ya entrega:
 * la carpeta donde viven las páginas de un tipo (`servicios/…`), su semántica
 * (`type.negocio.horario`), el título literal de su template (`# Horario`) y el nombre del modelo.
 *
 * SLDB no expone hoy cuántas páginas admite un tipo ni dónde declara que van (en minegocio,
 * `__pagina__`). Aquí solo se lee la evidencia del store: un tipo con varias páginas, o con sus
 * páginas en una carpeta, admite varias; un tipo con una sola página en la raíz es de página única.
 */
import type { GraphDocument, ModelCatalogEntry, Payload, SchemaField, SchemaModel } from "./contract";

export interface WikiPage {
  id: string;
  model: string;
  label: string;
}

/** Un tipo del que se puede agregar una página desde el índice. */
export interface WikiCreatable {
  model: string;
  /** El tipo en minúscula, para «+ Agregar servicio». */
  label: string;
}

export interface WikiGroup {
  key: string;
  label: string;
  pages: WikiPage[];
  creatable: WikiCreatable[];
}

const MARCA = /⸢([^⸥]*)⸥/g;

/** `identidad-visual` → «Identidad visual». */
export function humanize(text: string): string {
  const plain = text.replace(/[-_]+/g, " ").trim();
  return plain ? plain.charAt(0).toUpperCase() + plain.slice(1) : text;
}

/** `IdentidadVisualDoc` → «Identidad visual». */
export function typeLabel(model: string): string {
  const base = model.replace(/Doc$/, "") || model;
  return humanize(base.replace(/([a-z0-9])([A-Z])/g, "$1 $2").toLowerCase());
}

/** Identificador de página para un texto: minúsculas, sin tildes, con guiones (lo que admite `POST /save`). */
export function slug(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

/** El título (`# …`) del template: su texto literal y, si lo lleva, el field que muestra. */
export function templateTitle(template: string | undefined): { literal: string; field: string | null } | null {
  if (!template) return null;
  const body = template.replace(/^---\n[\s\S]*?\n---\n?/, "");
  const line = /^#\s+(.+)$/m.exec(body)?.[1];
  if (line === undefined) return null;
  const fields = Array.from(line.matchAll(MARCA), (m) => (m[1] ?? "").split("•").pop() ?? "");
  return { literal: line.replace(MARCA, "").trim(), field: fields[0] || null };
}

/** Los rasgos con que el template marca cada field (`⸢rev,dict•atencion⸥` → atencion: rev, dict). */
export function templateTraits(template: string | undefined): Map<string, string[]> {
  const traits = new Map<string, string[]>();
  for (const match of (template ?? "").matchAll(MARCA)) {
    const [head, path] = (match[1] ?? "").split("•");
    if (path && !traits.has(path)) traits.set(path, (head ?? "").split(",").map((t) => t.trim()));
  }
  return traits;
}

/** El paquete de una semántica `type.paquete.catalogo.servicio` → `catalogo`; `type.negocio.horario` → `negocio`. */
function semanticPackage(tags: string[] | undefined): string | null {
  const tag = tags?.find((t) => t.startsWith("type."));
  if (!tag) return null;
  const parts = tag.split(".").slice(1);
  if (parts[0] === "paquete") parts.shift();
  return parts[0] ?? null;
}

function folderOf(path: string): string | null {
  const parts = path.split("/").filter(Boolean);
  return parts.length > 1 ? parts[0]! : null;
}

/** ¿El store muestra que este tipo lleva varias páginas? (varias, o en una carpeta propia). */
export function allowsMany(docs: GraphDocument[]): boolean {
  return docs.length > 1 || docs.some((d) => folderOf(d.path) !== null);
}

function textOf(payload: Payload | undefined, key: string | null | undefined): string | null {
  const value = key ? payload?.[key] : undefined;
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** El nombre con que una página aparece en el índice. */
export function pageLabel(doc: GraphDocument, many: boolean, schema?: SchemaModel): string {
  const title = templateTitle(schema?.template);
  if (many) {
    return (
      textOf(doc.payload, title?.field) ??
      textOf(doc.payload, "title") ??
      textOf(doc.payload, "nombre") ??
      textOf(doc.payload, "name") ??
      humanize(doc.id)
    );
  }
  return title?.literal || textOf(doc.payload, "title") || typeLabel(doc.model_name);
}

/** El nombre del negocio: el campo `nombre` de su página `NegocioDoc`, si existe. */
export function businessName(documents: GraphDocument[]): string | null {
  return textOf(documents.find((d) => d.model_name === "NegocioDoc")?.payload, "nombre");
}

export function buildWikiIndex(
  documents: GraphDocument[],
  models: ModelCatalogEntry[],
  schemaModels: SchemaModel[] = [],
): WikiGroup[] {
  const order: string[] = [];
  const seen = new Set<string>();
  for (const name of [...schemaModels.map((m) => m.id), ...documents.map((d) => d.model_name), ...models.map((m) => m.name)]) {
    if (!seen.has(name)) {
      seen.add(name);
      order.push(name);
    }
  }
  const schemaOf = new Map(schemaModels.map((m) => [m.id, m]));
  const catalogOf = new Map(models.map((m) => [m.name, m]));
  const groups = new Map<string, WikiGroup>();

  for (const model of order) {
    const docs = documents.filter((d) => d.model_name === model);
    const many = allowsMany(docs);
    const folder = docs.map((d) => folderOf(d.path)).find((f) => f !== null && f !== model) ?? null;
    const key = folder ?? semanticPackage(catalogOf.get(model)?.semantics ?? docs[0]?.semantic_tags) ?? typeLabel(model);
    const group = groups.get(key) ?? { key, label: humanize(key), pages: [], creatable: [] };
    groups.set(key, group);
    for (const doc of docs) group.pages.push({ id: doc.id, model, label: pageLabel(doc, many, schemaOf.get(model)) });
    if (many || docs.length === 0) group.creatable.push({ model, label: typeLabel(model).toLowerCase() });
  }
  return Array.from(groups.values());
}

// ---------------------------------------------------------------- página nueva

export interface NewPageField {
  field: SchemaField;
  /** Markdown de varias líneas (rasgo `markdown` del template): se escribe en un área de texto. */
  long: boolean;
}

export interface NewPagePlan {
  /** Los campos obligatorios que la persona tiene que escribir. */
  fields: NewPageField[];
  /** Obligatorios con estructura (grupo o lista): parten vacíos y se completan en la página. */
  preset: Payload;
  /** El campo del que sale el identificador de la página, si el tipo lo tiene. */
  nameField: string | null;
}

/** Qué pedir para crear una página de un tipo: sus campos obligatorios, según el schema del store. */
export function planNewPage(schema: SchemaModel | undefined): NewPagePlan {
  const traits = templateTraits(schema?.template);
  const fields: NewPageField[] = [];
  const preset: Payload = {};
  for (const field of schema?.fields ?? []) {
    if (!field.required) continue;
    const own = traits.get(field.name) ?? [];
    if (own.includes("dict")) preset[field.name] = {};
    else if (own.includes("list") || field.kind === "list" || field.kind === "stringlist") preset[field.name] = [];
    else fields.push({ field, long: own.includes("markdown") });
  }
  const titleField = templateTitle(schema?.template)?.field ?? null;
  const candidates = [titleField, "nombre", "title", "name"];
  const nameField = candidates.find((c) => c && fields.some((f) => f.field.name === c && f.field.kind === "string")) ?? null;
  return { fields, preset, nameField };
}

/** El texto de un control, como el valor que viaja a SLDB. No valida: lo que no calza lo rechaza el store. */
export function typedValue(field: SchemaField, text: string): unknown {
  const trimmed = text.trim();
  const numeric = /^-?\d+(\.\d+)?$/.test(trimmed);
  if (field.kind === "boolean") return trimmed === "true";
  if ((field.kind === "integer" || field.kind === "number" || field.kind === "unknown") && numeric) return Number(trimmed);
  return trimmed;
}

/** El payload de una página nueva: lo escrito, más los obligatorios con estructura vacíos. Lo vacío no viaja. */
export function newPagePayload(plan: NewPagePlan, texts: Record<string, string>): Payload {
  const payload: Payload = { ...plan.preset };
  for (const { field } of plan.fields) {
    const text = texts[field.name] ?? "";
    if (field.kind === "boolean" || text.trim()) payload[field.name] = typedValue(field, text);
  }
  return payload;
}

/**
 * El identificador de la página nueva: el nombre escrito, o el del tipo si el tipo no tiene campo
 * de nombre. Con el nombre en blanco también va el del tipo: así SLDB responde con lo que falta
 * (el nombre obligatorio) y no con un reclamo por el identificador.
 */
export function newPageId(model: string, plan: NewPagePlan, texts: Record<string, string>): string {
  return (plan.nameField && slug(texts[plan.nameField] ?? "")) || slug(typeLabel(model));
}
