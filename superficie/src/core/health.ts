/**
 * Salud del store. Dos orígenes distintos, y no hay que confundirlos:
 *
 * - SERVIDO por SLDB: `/lint`, `/graph/isolated`, `/graph/cycles`. Existen en
 *   `cli/serve/routes.py` y `graph_ui` ya los consume. No se derivan acá.
 * - DERIVADO en el cliente: ruido estructural y `canonical:false`, que salen de
 *   sondear `/document/segments` documento por documento.
 *
 * El hallazgo derivado principal es RUIDO ESTRUCTURAL: un heading dentro del valor
 * de un field es una sección que el modelo no declara. No es corrupción del
 * documento (extrae y renderiza byte a byte); es un contrato incompleto. La salida
 * es un modelo que herede del actual y declare esas secciones como campos `optrev`.
 */
import type {
  DocumentFinding,
  DocumentSegments,
  GraphDocument,
  GraphNodeRef,
  HealthReport,
  StoresCheck,
  LintProblem,
  Segment,
  StructuralNoiseFinding,
} from "./contract";
import { type SldbClient } from "./client";
import { isolatedDocuments, parseNodes } from "./graph-nodes";

/** Marcadores cuyo `text` es un valor de field: si traen headings, el modelo no los declara. */
const VALUE_MARKERS = new Set(["rev", "optrev"]);

const HEADING = /^#{1,6}[ \t]+(.+?)[ \t]*$/gm;

function* walk(segments: Segment[]): Generator<Segment> {
  for (const segment of segments) {
    yield segment;
    if ("children" in segment) yield* walk(segment.children);
  }
}

/** Títulos de los headings que viven dentro de valores de field (secciones sin declarar). */
export function undeclaredHeadings(segments: DocumentSegments): string[] {
  const titles: string[] = [];
  for (const segment of walk(segments.segments)) {
    if (segment.type !== "field" || !VALUE_MARKERS.has(segment.marker)) continue;
    for (const match of segment.text.matchAll(HEADING)) {
      const title = match[1]?.trim();
      if (title) titles.push(title);
    }
  }
  return titles;
}

function noiseOf(doc: GraphDocument, segments: DocumentSegments): StructuralNoiseFinding | null {
  const headings = undeclaredHeadings(segments);
  return headings.length > 0 ? { doc: doc.id, model: doc.model_name, path: doc.path, headings } : null;
}

/**
 * Lo que SLDB ya analiza. Cada pieza falla por separado y devuelve `null`: una ruta
 * ausente se reporta como "no disponible", nunca como "sin problemas". Un cliente
 * que no implemente el método cae en el mismo camino que un 404.
 */
export async function collectServedHealth(client: SldbClient): Promise<{
  lint: LintProblem[] | null;
  isolated: GraphNodeRef[] | null;
  cycles: GraphNodeRef[][] | null;
  storeCheck: StoresCheck | null;
}> {
  const attempt = async <T>(run: () => Promise<T> | undefined): Promise<T | null> => {
    try {
      return (await run()) ?? null;
    } catch {
      return null;
    }
  };
  const [lint, isolated, cycles, storeCheck] = await Promise.all([
    attempt(() => client.lint?.().then((r) => r.problems)),
    attempt(() => client.isolated?.().then(isolatedDocuments)),
    attempt(() => client.cycles?.().then((cs) => cs.map(parseNodes))),
    attempt(() => client.storesCheck?.()),
  ]);
  return { lint, isolated, cycles, storeCheck };
}

/** Sondea `/document/segments` de cada documento del grafo y resume los hallazgos. */
export async function collectHealth(
  client: SldbClient,
  docs: GraphDocument[],
  modelErrors: { model: string; error: string }[] = [],
  onProgress?: (done: number, total: number) => void,
): Promise<HealthReport> {
  const structural: StructuralNoiseFinding[] = [];
  const noncanonical: DocumentFinding[] = [];
  const unreadable: DocumentFinding[] = [];

  const served = await collectServedHealth(client);

  let done = 0;
  for (const doc of docs) {
    const where = { doc: doc.id, model: doc.model_name, path: doc.path };
    try {
      const segments = await client.segments(doc.id);
      const noise = noiseOf(doc, segments);
      if (noise) structural.push(noise);
      if (segments.canonical === false) noncanonical.push({ ...where, detail: "El archivo en disco no coincide con el render del payload." });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      unreadable.push({ ...where, detail });
    }
    onProgress?.(++done, docs.length);
  }

  return { structural, noncanonical, unreadable, modelErrors, checked: docs.length, ...served };
}

/** Una divergencia de `/stores/check`: qué se rompió, dónde y por qué (`explain` es del servidor). */
export interface StoreDivergence {
  scope: "store" | "model" | "document";
  model?: string;
  doc?: string;
  path?: string;
  kind: "raiz" | "contrato" | "roster" | "archivo-borrado" | "contenido" | "campos";
  detail: string;
}

/**
 * Lo que `/stores/check` reporta como roto, una entrada por causa. Un store sano da `[]`;
 * eso vale solo cuando la ruta respondió (si no, `storeCheck` es `null` y no se llama acá).
 */
export function storeDivergences(check: StoresCheck): StoreDivergence[] {
  const out: StoreDivergence[] = [];
  if (!check.root_ok || !check.hash_a_ok) out.push({ scope: "store", kind: "raiz", detail: check.summary });
  for (const model of check.models) {
    if (!model.contract_ok) out.push({ scope: "model", model: model.name, kind: "contrato", detail: "El contrato del modelo no coincide con el registrado." });
    if (!model.roster_ok) out.push({ scope: "model", model: model.name, kind: "roster", detail: "La lista de documentos del modelo no coincide con el índice." });
    for (const d of model.documents) {
      const where = { scope: "document" as const, model: model.name, doc: d.name, path: d.path };
      if (!d.path_exists) out.push({ ...where, kind: "archivo-borrado", detail: d.explain || "El archivo ya no existe en disco." });
      else if (!d.content_ok) out.push({ ...where, kind: "contenido", detail: d.explain || "El contenido del archivo cambió respecto de lo indexado." });
      else if (!d.fields_ok) out.push({ ...where, kind: "campos", detail: d.explain || "Los campos extraídos no coinciden con lo indexado." });
    }
  }
  return out;
}
