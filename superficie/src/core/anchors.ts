/**
 * LECTOR · anclar sobre texto crudo (§6.1, §16).
 *
 * El modelo no vive acá: los campos del formulario y del payload salen del schema
 * que responde `/schema`. Este store registra `pron.models:AnchorDoc` (`symbol`,
 * `forms`, `ref`, `steps`, `motive`), sin `kind`/`tags`/`provenance`; otro store
 * puede registrar `sldb.models.anchor_doc` con esos campos. Las dos variantes
 * funcionan porque nada se hardcodea: se manda solo lo que el modelo declara.
 *
 * La validación de `ref` no inventa un patrón: si el schema declara `pattern` en el
 * field, se valida con ESE patrón. Sin `pattern` declarado, `ref` queda libre.
 *
 * `DuplicateWarning` (§6.1): antes de crear un anchor se consulta `GET /corpus/rank` con
 * el texto anclado. Acá vive la lógica pura (armar la consulta, decidir si consultar,
 * clasificar hits de campo en duplicado/parecido); la vista hace la llamada y muestra los tres
 * estados. El aviso es informativo: nunca bloquea ni cambia la creación.
 */
import type { FieldRankHit, Payload, SchemaField, SchemaModel } from "./contract";
import { above, DUPLICATE_THRESHOLD, queryText, SUGGEST_THRESHOLD } from "./similarity";

/** Conteo de palabras que se toman de la selección para sugerir el símbolo. */
export const SUGGESTED_SYMBOL_MAX_WORDS = 4;

/** Prefijo del id: `AnchorDoc.symbol` "el documento se llama anchor-<symbol>". */
export const ANCHOR_ID_PREFIX = "anchor-";

/** El id con el que `POST /save` crea el documento: tiene que ser un nombre válido. */
export const DOCUMENT_ID = /^[a-zA-Z0-9][a-zA-Z0-9_-]*$/;

/** Un tramo de texto seleccionado, con su cita exacta y sus líneas 1-based inclusive. */
export interface AnchorSelection {
  quote: string;
  start: number;
  end: number;
  startLine: number;
  endLine: number;
}

/** Un anchor creado en esta sesión: lo que se marca en el texto y lo que se lista. */
export interface SessionAnchor {
  id: string;
  symbol: string;
  quote: string;
  start: number;
  end: number;
  startLine: number;
  endLine: number;
}

export interface DraftError {
  field: string;
  message: string;
}

/** Cómo se edita un campo declarado: el formulario se arma desde el schema, no a mano. */
export type AnchorInputKind = "text" | "textarea" | "select" | "json" | "number" | "boolean";

/** Línea 1-based de un índice de carácter (el índice apunta dentro del texto). */
export function lineOf(text: string, index: number): number {
  const limit = Math.max(0, Math.min(index, text.length));
  let line = 1;
  for (let i = 0; i < limit; i += 1) if (text[i] === "\n") line += 1;
  return line;
}

/** Selección cruda → cita + líneas. `null` si el tramo está vacío. */
export function selectionAt(text: string, start: number, end: number): AnchorSelection | null {
  const from = Math.max(0, Math.min(start, text.length));
  const to = Math.max(0, Math.min(end, text.length));
  if (to - from <= 0) return null;
  return {
    quote: text.slice(from, to),
    start: from,
    end: to,
    startLine: lineOf(text, from),
    endLine: lineOf(text, to - 1),
  };
}

/** "no será posible una conexión" → "no-sera-posible-una". */
export function slugify(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** Símbolo sugerido desde la selección: pocas palabras, slugificadas. Editable después. */
export function suggestSymbol(quote: string, maxWords = SUGGESTED_SYMBOL_MAX_WORDS): string {
  const words = slugify(quote)
    .split("-")
    .filter(Boolean)
    .slice(0, Math.max(1, maxWords));
  const symbol = words.join("-");
  return symbol.length > 60 ? symbol.slice(0, 60).replace(/-+$/, "") : symbol;
}

/** `symbol` → `anchor-<symbol>`, sin duplicar el prefijo si ya lo trae. */
export function anchorIdFor(symbol: string): string {
  const slug = slugify(symbol).replace(/^anchor-/, "");
  return slug ? `${ANCHOR_ID_PREFIX}${slug}` : ANCHOR_ID_PREFIX;
}

/** El modelo de anchors del schema: `AnchorDoc` o la variante que el store registre. */
export function findAnchorModel(models: SchemaModel[], preferredId = "AnchorDoc"): SchemaModel | null {
  const named = models.find((model) => model.id === preferredId);
  if (named) return named;
  return models.find((model) => /anchor/i.test(model.id) || /anchor/i.test(model.model_ref)) ?? null;
}

/** Cómo se edita un field declarado, según su kind. */
export function inputForField(field: SchemaField): AnchorInputKind {
  if (field.kind === "enum") return "select";
  if (field.kind === "boolean") return "boolean";
  if (field.kind === "integer" || field.kind === "number") return "number";
  if (field.kind === "stringlist" || field.kind === "enumlist" || field.kind === "list" || field.kind === "object") return "json";
  if (field.kind === "string") return field.name === "motive" ? "textarea" : "text";
  return "text";
}

/** Draft vacío con todos los campos declarados. */
export function emptyDraft(model: SchemaModel): Record<string, string> {
  return Object.fromEntries(model.fields.map((field) => [field.name, ""]));
}

/** Draft inicial: símbolo sugerido desde la cita, el resto en blanco. */
export function draftFromSelection(model: SchemaModel, selection: AnchorSelection): Record<string, string> {
  const draft = emptyDraft(model);
  if (model.fields.some((field) => field.name === "symbol")) draft.symbol = suggestSymbol(selection.quote);
  return draft;
}

function parseJson(raw: string): { ok: true; value: unknown } | { ok: false } {
  try {
    return { ok: true, value: JSON.parse(raw) };
  } catch {
    return { ok: false };
  }
}

/** JSON array, o lista separada por comas. Es lo que un `stringlist` acepta en el template. */
export function toStringList(raw: string): string[] {
  const trimmed = raw.trim();
  if (trimmed === "") return [];
  const parsed = parseJson(trimmed);
  if (parsed.ok && Array.isArray(parsed.value)) return parsed.value.filter((item): item is string => typeof item === "string");
  return trimmed
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function matchesPattern(pattern: string, value: string): boolean {
  try {
    return new RegExp(pattern).test(value);
  } catch {
    // Un patrón inválido lo declara el store, no esta vista: no bloquea el formulario.
    return true;
  }
}

/** Errores del draft contra el schema real, incluido el `pattern` declarado por el field. */
export function validateDraft(draft: Record<string, string>, model: SchemaModel): DraftError[] {
  const errors: DraftError[] = [];
  for (const field of model.fields) {
    const trimmed = (draft[field.name] ?? "").trim();
    if (trimmed === "") {
      if (field.required) errors.push({ field: field.name, message: `«${field.name}» es obligatorio.` });
      continue;
    }
    if (field.pattern && !matchesPattern(field.pattern, trimmed)) {
      errors.push({ field: field.name, message: `«${field.name}» no coincide con el patrón ${field.pattern}.` });
    }
    if (field.kind === "enum" && Array.isArray(field.enum) && !field.enum.some((value) => String(value) === trimmed)) {
      errors.push({ field: field.name, message: `«${field.name}» debe ser uno de: ${field.enum.map((value) => String(value)).join(", ")}.` });
    }
    if (field.kind === "integer" && !/^-?\d+$/.test(trimmed)) {
      errors.push({ field: field.name, message: `«${field.name}» debe ser un entero.` });
    }
    if (field.kind === "number" && !Number.isFinite(Number(trimmed))) {
      errors.push({ field: field.name, message: `«${field.name}» debe ser un número.` });
    }
    if ((field.kind === "list" || field.kind === "object") && !parseJson(trimmed).ok) {
      errors.push({ field: field.name, message: `«${field.name}» debe ser JSON válido.` });
    }
    if (field.kind === "boolean" && trimmed !== "true" && trimmed !== "false") {
      errors.push({ field: field.name, message: `«${field.name}» debe ser true o false.` });
    }
  }
  return errors;
}

function convert(field: SchemaField, raw: string): { ok: true; value: unknown } | { ok: false; message: string } {
  const trimmed = raw.trim();
  if (field.kind === "stringlist" || field.kind === "enumlist") return { ok: true, value: toStringList(raw) };
  if (field.kind === "list" || field.kind === "object") {
    const parsed = parseJson(trimmed);
    if (!parsed.ok) return { ok: false, message: `«${field.name}» debe ser JSON válido.` };
    return { ok: true, value: parsed.value };
  }
  if (field.kind === "integer") return { ok: true, value: Number.parseInt(trimmed, 10) };
  if (field.kind === "number") return { ok: true, value: Number(trimmed) };
  if (field.kind === "boolean") return { ok: true, value: trimmed === "true" };
  return { ok: true, value: trimmed };
}

/**
 * Payload para `POST /save`: SOLO los campos que el modelo declara. Un campo que
 * el modelo no declara no se manda, aunque el draft lo traiga.
 *
 * Se incluyen los requeridos siempre y los opcionales con valor; un opcional vacío
 * se omite para que el modelo aplique su default.
 */
export function buildPayload(draft: Record<string, string>, model: SchemaModel): { payload: Payload; errors: DraftError[] } {
  const errors = validateDraft(draft, model);
  if (errors.length > 0) return { payload: {}, errors };
  const payload: Payload = {};
  for (const field of model.fields) {
    const raw = draft[field.name] ?? "";
    if (raw.trim() === "" && !field.required) continue;
    const converted = convert(field, raw);
    if (!converted.ok) return { payload: {}, errors: [{ field: field.name, message: converted.message }] };
    payload[field.name] = converted.value;
  }
  return { payload, errors: [] };
}

export interface MarkedRun {
  text: string;
  anchor: SessionAnchor | null;
}

/**
 * Corta el texto en tramos marcados y literales, en orden. Un anchor que pisa a
 * otro ya aceptado se descarta: los tramos marcados no se superponen.
 */
export function splitByAnchors(text: string, anchors: SessionAnchor[]): MarkedRun[] {
  const valid = anchors
    .filter((anchor) => anchor.start >= 0 && anchor.end > anchor.start && anchor.end <= text.length)
    .sort((a, b) => a.start - b.start || b.end - a.end);
  const accepted: SessionAnchor[] = [];
  let boundary = -1;
  for (const anchor of valid) {
    if (anchor.start < boundary) continue;
    accepted.push(anchor);
    boundary = anchor.end;
  }
  const runs: MarkedRun[] = [];
  let cursor = 0;
  for (const anchor of accepted) {
    if (anchor.start > cursor) runs.push({ text: text.slice(cursor, anchor.start), anchor: null });
    runs.push({ text: text.slice(anchor.start, anchor.end), anchor });
    cursor = anchor.end;
  }
  if (cursor < text.length) runs.push({ text: text.slice(cursor), anchor: null });
  return runs;
}

/** Cita corta para listar sin romper el panel. */
export function shortenQuote(quote: string, max = 140): string {
  const flat = quote.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max)}…` : flat;
}

/** Etiqueta de líneas 1-based: `línea 47` o `líneas 47–48`. */
export function lineLabel(selection: Pick<AnchorSelection, "startLine" | "endLine">): string {
  return selection.startLine === selection.endLine
    ? `línea ${selection.startLine}`
    : `líneas ${selection.startLine}–${selection.endLine}`;
}

/** Menos caracteres que esto no dan un parecido con sentido: no se consulta. */
export const MIN_DUPLICATE_QUERY_CHARS = 12;
/** Espera tras el último cambio de selección antes de consultar. */
export const DUPLICATE_DEBOUNCE_MS = 400;
/** Cuántos parecidos se piden y se muestran. */
export const DUPLICATE_HITS = 3;

/** Consulta para `rank` a partir de la cita anclada; `null` si es muy corta para consultar. */
export function duplicateQuery(quote: string | null | undefined, min = MIN_DUPLICATE_QUERY_CHARS): string | null {
  const q = queryText(quote ?? "");
  return q.length >= min ? q : null;
}

/**
 * Parámetros de `client.rank` para el aviso. Se compara contra CAMPOS (`fields: true`): el
 * índice por documento diluye el parecido (concatena todos los strings del payload) y nunca
 * llega al umbral de duplicado. `refresh` solo cuando el usuario pide indexar, y con el mismo
 * modo `fields`, porque el índice de campos es distinto del de documentos.
 */
export function duplicateRankParams(q: string, refresh = false) {
  return { q, k: DUPLICATE_HITS, threshold: SUGGEST_THRESHOLD, fields: true as const, refresh };
}

export interface ClassifiedHits {
  /** Puntaje >= DUPLICATE_THRESHOLD: posible duplicado. */
  duplicates: FieldRankHit[];
  /** Puntaje entre SUGGEST_THRESHOLD y DUPLICATE_THRESHOLD: parecido. */
  similar: FieldRankHit[];
}

/** Separa los hits en duplicados y parecidos (mejores primero); descarta lo bajo el umbral. */
export function classifyHits(hits: FieldRankHit[]): ClassifiedHits {
  const kept = above(hits, SUGGEST_THRESHOLD).slice(0, DUPLICATE_HITS);
  return {
    duplicates: kept.filter((hit) => hit.score >= DUPLICATE_THRESHOLD),
    similar: kept.filter((hit) => hit.score < DUPLICATE_THRESHOLD),
  };
}

/** Puntaje 0 a 1 como porcentaje entero para mostrar. */
export function scorePercent(score: number): number {
  return Math.round(Math.max(0, Math.min(1, score)) * 100);
}
