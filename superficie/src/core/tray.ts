/**
 * BANDEJA · lo anotado sin ubicar (§6.4).
 *
 * La bandeja LISTA lo que no tiene lugar y SUGIERE destino: los documentos ya
 * ubicados (los que no están en la bandeja) más parecidos, según `GET /corpus/rank`.
 * El índice compara texto con difflib, así que el puntaje mide parecido de texto,
 * no de significado, y se muestra siempre. Nada se aplica solo. Si el servidor no
 * responde o el corpus no está indexado se dice; nunca se inventa un ranking.
 * Aquí vive la lógica pura (consulta, universo `among`, orden y tope); el pedido
 * HTTP está en la vista.
 *
 * Lo que entra a la bandeja, derivable de `/graph` y `/schema`:
 *
 * - SIN PROCEDENCIA: el documento declara `provenance` en su modelo y lo tiene
 *   vacío. Regla 2 de la propuesta: "todo atom tiene origen; sin provenance no es
 *   conocimiento, es opinión". Es el criterio de bandeja que el store sí sostiene.
 * - SIN UBICAR POR TAG: `status:draft` y equivalentes, cuando se usen.
 *
 * Un documento cuyo modelo NO declara `provenance` no es un borrador: es un tipo
 * de documento al que la procedencia no le aplica. Distinguirlo es el punto.
 */
import type { GraphDocument, RankHit, SchemaIndexLike } from "./contract";
import { above, queryText, SUGGEST_THRESHOLD } from "./similarity";

/** Tags que marcan algo anotado y todavía sin ubicar. */
const DRAFT_TAGS = new Set(["status:draft", "status:borrador", "draft", "borrador"]);

export type TrayReason = "sin-procedencia" | "marcado-borrador";

export interface TrayEntry {
  doc: string;
  model: string;
  path: string;
  title: string;
  reasons: TrayReason[];
  /** Texto corto del documento, para reconocerlo sin abrirlo. */
  excerpt: string;
}

function textOf(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function tagsOf(doc: GraphDocument): string[] {
  const tags = doc.payload.tags;
  return Array.isArray(tags) ? tags.filter((tag): tag is string => typeof tag === "string") : [];
}

export function isDraftTagged(doc: GraphDocument): boolean {
  return tagsOf(doc).some((tag) => DRAFT_TAGS.has(tag.toLowerCase()));
}

/**
 * `true` solo si el modelo DECLARA `provenance` y el documento lo tiene vacío.
 * Si el modelo no lo declara, la procedencia no aplica y el documento no es un
 * borrador: devolver `true` ahí llenaría la bandeja de ruido.
 */
export function lacksProvenance(doc: GraphDocument, declares: (model: string, field: string) => boolean): boolean {
  if (!declares(doc.model_name, "provenance")) return false;
  return textOf(doc.payload.provenance) === "";
}

function excerptOf(doc: GraphDocument): string {
  const summary = textOf(doc.payload.summary) || textOf(doc.payload.answer) || textOf(doc.payload.motive);
  return summary.length > 220 ? `${summary.slice(0, 220)}…` : summary;
}

export function titleOf(doc: GraphDocument): string {
  return textOf(doc.payload.title) || doc.id;
}

/** Los documentos que están en la bandeja, con el motivo por el que cayeron ahí. */
export function collectTray(docs: GraphDocument[], schema: SchemaIndexLike | null): TrayEntry[] {
  const declares = (model: string, field: string) => (schema ? schema.field(model, field) !== undefined : false);
  const entries: TrayEntry[] = [];
  for (const doc of docs) {
    const reasons: TrayReason[] = [];
    if (isDraftTagged(doc)) reasons.push("marcado-borrador");
    if (lacksProvenance(doc, declares)) reasons.push("sin-procedencia");
    if (reasons.length === 0) continue;
    entries.push({ doc: doc.id, model: doc.model_name, path: doc.path, title: titleOf(doc), reasons, excerpt: excerptOf(doc) });
  }
  return entries;
}

/** Cuenta por modelo, para que la bandeja no sea una lista plana de 90 ítems. */
export function groupByModel(entries: TrayEntry[]): { model: string; entries: TrayEntry[] }[] {
  const byModel = new Map<string, TrayEntry[]>();
  for (const entry of entries) byModel.set(entry.model, [...(byModel.get(entry.model) ?? []), entry]);
  return [...byModel.entries()]
    .map(([model, list]) => ({ model, entries: list }))
    .sort((a, b) => b.entries.length - a.entries.length || a.model.localeCompare(b.model));
}

/** Cuántas sugerencias se muestran por documento. */
export const SUGGESTION_LIMIT = 3;

/** Título más todos los strings del payload (y de listas de strings), acotado por `queryText`. */
export function trayQuery(doc: GraphDocument): string {
  const parts: string[] = [titleOf(doc)];
  for (const value of Object.values(doc.payload)) {
    if (typeof value === "string") parts.push(value);
    else if (Array.isArray(value)) for (const item of value) if (typeof item === "string") parts.push(item);
  }
  return queryText(parts.join(" "));
}

/** Id con que el índice nombra un documento (`Model:name`), que es lo que acepta `among`. */
export const indexIdOf = (doc: Pick<GraphDocument, "id" | "model_name">): string => `${doc.model_name}:${doc.id}`;

/** Destinos posibles: los documentos que NO están en la bandeja. */
export function placedIds(docs: GraphDocument[], entries: TrayEntry[]): string[] {
  const inTray = new Set(entries.map((e) => e.doc));
  return docs.filter((d) => !inTray.has(d.id)).map(indexIdOf);
}

export interface Suggestion {
  /** Nombre del documento: el id de `#/doc/<name>`. */
  name: string;
  model: string;
  title: string;
  score: number;
  /** Puntaje en porcentaje entero, p. ej. 62. */
  percent: number;
}

/** Hasta `limit` hits que alcanzan el umbral, mejores primero, sin el propio documento. */
export function pickSuggestions(hits: RankHit[], self: string, threshold = SUGGEST_THRESHOLD, limit = SUGGESTION_LIMIT): Suggestion[] {
  return above(
    hits.filter((h) => h.name !== self),
    threshold,
  )
    .slice(0, limit)
    .map((h) => ({
      name: h.name,
      model: h.model,
      title: textOf(h.payload?.title) || h.name,
      score: h.score,
      percent: Math.round(h.score * 100),
    }));
}
