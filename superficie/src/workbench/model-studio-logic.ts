import type {
  ModelCatalogEntry,
  ModelDescription,
  ModelFieldDescriptor,
  ModelValidationReport,
} from "../core/contract";

/** Tipos que ofrece el formulario "+ Agregar campo". */
export const FIELD_TYPE_OPTIONS = [
  "str",
  "int",
  "float",
  "bool",
  "list[str]",
  "list[DocRef]",
  "DocRef[SpecDoc]",
  "DocRef[FuenteDoc]",
] as const;

export const AUTHORITY_OPTIONS = ["authored", "source_raw", "theorem", "generated", "cache"] as const;

export type FieldKind = "plain" | "composition" | "reference";

/** Marcador `⸢kind[,trait]•campo⸥` hallado en el texto de `__template__`. */
export interface TemplateMarker {
  kinds: string[];
  path: string;
  raw: string;
}

const MARKER_RE = /⸢([^•⸥\n]*)•([^⸥\n]+)⸥/g;

export function parseTemplateMarkers(template: string): TemplateMarker[] {
  const out: TemplateMarker[] = [];
  for (const m of (template ?? "").matchAll(MARKER_RE)) {
    out.push({
      kinds: (m[1] ?? "").split(",").map((s) => s.trim()).filter(Boolean),
      path: (m[2] ?? "").trim(),
      raw: m[0],
    });
  }
  return out;
}

/** Marcadores del template que tocan al campo (por nombre o por ruta `campo.sub`). */
export function markersForField(template: string, fieldName: string): TemplateMarker[] {
  return parseTemplateMarkers(template).filter(
    (m) => m.path === fieldName || m.path.startsWith(`${fieldName}.`) || m.path.startsWith(`${fieldName}[`),
  );
}

/** Insignia compacta `⸢rev⸥` / `⸢rev,list⸥` solo si el template marca el campo como reversible. */
export function reversibleBadge(template: string, fieldName: string): string | null {
  const rev = markersForField(template, fieldName).find((m) => m.kinds.some((k) => k === "rev" || k === "optrev"));
  return rev ? `⸢${rev.kinds.join(",")}⸥` : null;
}

/** Modelo objetivo dentro de una anotación (`DocRef[X]`, `Ref[X]`, `list[DocRef[X]]`), o null. */
export function annotationTargetModel(annotation: string): string | null {
  const m = /(?:DocRef|Ref)\[\s*"?([A-Za-z_][A-Za-z0-9_]*)"?\s*\]/.exec(annotation ?? "");
  return m?.[1] ?? null;
}

export function isListAnnotation(annotation: string): boolean {
  return /^\s*(?:list|List|Sequence)\[/.test(annotation ?? "");
}

function fieldByName(detail: ModelDescription, name: string | null | undefined): ModelFieldDescriptor | undefined {
  return name ? detail.fields.find((f) => f.name === name) : undefined;
}

export function fieldKind(detail: ModelDescription, field: ModelFieldDescriptor): FieldKind {
  const comps = Object.entries(detail.compositions ?? {});
  if (comps.some(([key, c]) => key === field.name || c.source_field === field.name)) return "composition";
  if ((detail.references ?? []).includes(field.name)) return "reference";
  if (/(?:DocRef|Ref)\[/.test(field.annotation ?? "")) return "reference";
  return "plain";
}

export const FIELD_GLYPH: Record<FieldKind, string> = { plain: "+", composition: "♦", reference: "○" };

export interface UmlNeighbour {
  model: string;
  kind: "composition" | "reference";
  field: string;
}

/**
 * Vecinos UML del modelo activo: `__compositions__` (rombo) y `__references__` (punteado),
 * restringidos a modelos del catálogo. Una composición gana sobre una referencia al mismo modelo.
 */
/** Prefijos `Model:` que aparecen en el valor (string o lista de strings) de `field` en documentos reales. */
export function observedRefModels(documents: { model_name: string; payload?: Record<string, unknown> | null }[], model: string, field: string): string[] {
  const seen = new Set<string>();
  const take = (v: unknown) => {
    if (typeof v !== "string") return;
    const m = /^([A-Z][A-Za-z0-9_]*):\S/.exec(v.trim());
    if (m) seen.add(m[1]!);
  };
  for (const d of documents) {
    if (d.model_name !== model) continue;
    const v = d.payload?.[field];
    if (Array.isArray(v)) v.forEach(take);
    else take(v);
  }
  return [...seen];
}

/**
 * Vecinos UML: composiciones y referencias del contrato. Si la anotación no nombra el modelo
 * destino (`list`, `str`), se usa el que aparece en los documentos reales del modelo (`documents`).
 */
export function deriveUmlNeighbours(
  detail: ModelDescription,
  catalog: ModelCatalogEntry[],
  documents: { model_name: string; payload?: Record<string, unknown> | null }[] = [],
): UmlNeighbour[] {
  const known = new Set(catalog.map((m) => m.name));
  const found = new Map<string, UmlNeighbour>();
  const add = (n: UmlNeighbour) => {
    if (n.model === detail.name || !known.has(n.model)) return;
    const prev = found.get(n.model);
    if (!prev || (prev.kind === "reference" && n.kind === "composition")) found.set(n.model, n);
  };
  for (const [key, comp] of Object.entries(detail.compositions ?? {})) {
    const field = comp.source_field ?? key;
    const target = comp.model ?? annotationTargetModel(fieldByName(detail, field)?.annotation ?? "");
    if (target) add({ model: target, kind: "composition", field });
  }
  const refNames = new Set(detail.references ?? []);
  for (const f of detail.fields) {
    const target = annotationTargetModel(f.annotation);
    if (target) {
      if (refNames.has(f.name) || /(?:DocRef|Ref)\[/.test(f.annotation)) add({ model: target, kind: "reference", field: f.name });
    } else if (refNames.has(f.name)) {
      for (const observed of observedRefModels(documents, detail.name, f.name)) {
        add({ model: observed, kind: "reference", field: f.name });
      }
    }
  }
  for (const name of refNames) {
    if (known.has(name) && !fieldByName(detail, name)) add({ model: name, kind: "reference", field: name });
  }
  return [...found.values()];
}

/** El reporte está limpio: ok/valid verdaderos y sin errores. */
export function isCleanReport(report: ModelValidationReport | null | undefined): boolean {
  if (!report) return false;
  if (report.ok === false || report.valid === false) return false;
  if ((report.errors ?? []).length > 0) return false;
  return Boolean(report.valid ?? report.ok);
}

export interface PromoteGateInput {
  editable: boolean;
  readOnlyReason?: string;
  hasDraft: boolean;
  templateDirty: boolean;
  /** Validación vigente: modelo y revisión del draft sobre los que corrió. */
  validation: { model: string; rev: number; report: ModelValidationReport } | null;
  model: string | null;
  rev: number;
}

export interface PromoteGate {
  enabled: boolean;
  reason: string;
}

/** Bug #8: promover exige un validate limpio sobre EL draft actual. */
export function promoteGate(i: PromoteGateInput): PromoteGate {
  if (!i.model) return { enabled: false, reason: "Sin modelo seleccionado." };
  if (!i.editable) return { enabled: false, reason: i.readOnlyReason || "Modelo de solo lectura." };
  if (!i.hasDraft) return { enabled: false, reason: "No hay draft pendiente que promover." };
  if (i.templateDirty) return { enabled: false, reason: "Hay cambios de plantilla sin guardar en el draft." };
  if (!i.validation || i.validation.model !== i.model || i.validation.rev !== i.rev) {
    return { enabled: false, reason: "Valida el draft actual antes de promover." };
  }
  if (!isCleanReport(i.validation.report)) {
    return { enabled: false, reason: "La validación reportó errores: corrígelos y valida de nuevo." };
  }
  return { enabled: true, reason: "Draft validado sin errores." };
}

// ---------- Layout del diagrama UML ----------

export const UML = { rootW: 285, nodeW: 190, gap: 28, pad: 16, header: 24, extendsRow: 16, line: 15, body: 14 } as const;

export function boxHeight(fieldCount: number, hasBase: boolean): number {
  return UML.header + (hasBase ? UML.extendsRow : 0) + UML.body + fieldCount * UML.line;
}

export interface UmlBoxLayout {
  model: string;
  x: number;
  y: number;
  w: number;
  h: number;
  root: boolean;
}

export interface UmlConnector {
  from: string;
  to: string;
  kind: "composition" | "reference";
  field: string;
  path: string;
}

export interface UmlLayout {
  boxes: UmlBoxLayout[];
  connectors: UmlConnector[];
  width: number;
  height: number;
}

export function layoutUml(
  rootName: string,
  rootBox: { fields: number; hasBase: boolean },
  neighbours: UmlNeighbour[],
  boxInfo: Record<string, { fields: number; hasBase: boolean }>,
): UmlLayout {
  const { pad, gap, rootW, nodeW } = UML;
  const rootH = boxHeight(rootBox.fields, rootBox.hasBase);
  const boxes: UmlBoxLayout[] = [{ model: rootName, x: pad, y: pad, w: rootW, h: rootH, root: true }];
  const cols = 2;
  const rowTop: number[] = [];
  let y = pad + rootH + gap * 2;
  for (let start = 0; start < neighbours.length; start += cols) {
    const row = neighbours.slice(start, start + cols);
    const rowH = Math.max(...row.map((n) => boxHeight(boxInfo[n.model]?.fields ?? 0, boxInfo[n.model]?.hasBase ?? false)));
    row.forEach((n, c) => {
      const info = boxInfo[n.model] ?? { fields: 0, hasBase: false };
      boxes.push({ model: n.model, x: pad + c * (nodeW + gap), y, w: nodeW, h: boxHeight(info.fields, info.hasBase), root: false });
    });
    rowTop.push(y);
    y += rowH + gap * 2;
  }
  const connectors: UmlConnector[] = neighbours.map((n, i) => {
    const box = boxes.find((b) => b.model === n.model)!;
    const sx = pad + 40 + (i % 5) * 30;
    const tx = box.x + box.w / 2;
    const sy = pad + rootH;
    const midY = box.y - gap;
    // Rutas ortogonales: baja desde el borde inferior de la raíz y entra por arriba.
    const path = `M ${sx} ${sy} L ${sx} ${midY} L ${tx} ${midY} L ${tx} ${box.y}`;
    return { from: rootName, to: n.model, kind: n.kind, field: n.field, path };
  });
  return { boxes, connectors, width: pad * 2 + cols * nodeW + gap, height: Math.max(y - gap, pad * 2 + rootH) };
}
