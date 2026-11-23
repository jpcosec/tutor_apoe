/**
 * El índice de la wiki: las páginas del store agrupadas por tipo, con nombres para personas.
 *
 * Los grupos salen de lo que el store ya entrega: la carpeta donde viven las páginas de un tipo
 * (`agent/…`, `knowledge/…`), su semántica (`type.governance.agent`), el título de su template y
 * el nombre del modelo. Lo propio del tutor (qué tipos son su configuración y cómo se llaman las
 * carpetas de su base) viene de `core/tutor`.
 *
 * Aquí no se crean ni se quitan páginas: la configuración del tutor es un conjunto fijo de
 * páginas, y el resto de la base se genera desde `desk/atoms/`.
 */
import type { GraphDocument, ModelCatalogEntry, Payload, SchemaModel } from "./contract";
import { CONFIG_MODELS, GROUP_LABELS } from "./tutor";

export interface WikiPage {
  id: string;
  model: string;
  label: string;
}

export interface WikiGroup {
  key: string;
  label: string;
  pages: WikiPage[];
  /** Sus páginas son configuración del tutor: se editan aquí. Las demás se generan y solo se leen. */
  editable: boolean;
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

/** El título (`# …`) del template: su texto literal y, si lo lleva, el field que muestra. */
export function templateTitle(template: string | undefined): { literal: string; field: string | null } | null {
  if (!template) return null;
  const body = template.replace(/^---\n[\s\S]*?\n---\n?/, "");
  const line = /^#\s+(.+)$/m.exec(body)?.[1];
  if (line === undefined) return null;
  const fields = Array.from(line.matchAll(MARCA), (m) => (m[1] ?? "").split("•").pop() ?? "");
  return { literal: line.replace(MARCA, "").trim(), field: fields[0] || null };
}

/** El grupo de una semántica `type.governance.agent` → `governance`. */
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

/** ¿Las páginas de este tipo son configuración del tutor? */
export function isConfigModel(model: string): boolean {
  return CONFIG_MODELS.includes(model);
}

/** La primera página de configuración del store: la que se abre al entrar. */
export function configPage(documents: GraphDocument[]): GraphDocument | null {
  return documents.find((d) => isConfigModel(d.model_name)) ?? null;
}

/** El nombre del tutor: el `title` de su página de configuración, si existe. */
export function tutorName(documents: GraphDocument[]): string | null {
  return textOf(configPage(documents)?.payload, "title");
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
    if (docs.length === 0) continue; // un tipo sin páginas no tiene nada que mostrar: aquí no se crean
    const group = groups.get(key) ?? { key, label: GROUP_LABELS[key] ?? humanize(key), pages: [], editable: false };
    groups.set(key, group);
    if (isConfigModel(model)) group.editable = true;
    for (const doc of docs) group.pages.push({ id: doc.id, model, label: pageLabel(doc, many, schemaOf.get(model)) });
  }
  // La configuración primero; el resto, en el orden del schema.
  const all = Array.from(groups.values());
  return [...all.filter((g) => g.editable), ...all.filter((g) => !g.editable)];
}
