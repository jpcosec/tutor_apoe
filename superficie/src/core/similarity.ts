/**
 * Ayudas puras para las vistas que usan similitud (`/corpus/rank`). El índice HTTP compara
 * con difflib (no hay embedder por defecto): los puntajes son 0 a 1 y miden parecido de
 * texto, no de significado. Por eso los umbrales son conservadores y se ven en pantalla.
 */
import type { FieldRankHit, RankHit, SimilarityResult } from "./contract";

/** A partir de acá un texto se considera casi el mismo: sirve para avisar de un duplicado. */
export const DUPLICATE_THRESHOLD = 0.85;
/** A partir de acá vale la pena sugerir un destino o un parecido (siempre con su puntaje). */
export const SUGGEST_THRESHOLD = 0.35;
/** Largo máximo de la consulta: difflib es cuadrático y un documento entero no aporta más. */
export const QUERY_MAX_CHARS = 400;

/** Consulta acotada y sin espacios de sobra; vacía si no hay texto que comparar. */
export function queryText(text: string, max = QUERY_MAX_CHARS): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? flat.slice(0, max) : flat;
}

/** Nombre del documento de un hit (`Model:name` → `name`), que es el id de `#/doc/<id>`. */
export const docIdOf = (hit: Pick<RankHit, "name">): string => hit.name;

/** Ordena de mayor a menor puntaje sin mutar. */
export function byScore<T extends { score: number }>(hits: T[]): T[] {
  return [...hits].sort((a, b) => b.score - a.score);
}

/** Los hits que alcanzan el umbral, mejores primero. */
export function above<T extends { score: number }>(hits: T[], threshold: number): T[] {
  return byScore(hits).filter((h) => h.score >= threshold);
}

/** Texto del hit de campo (`docs/Model/doc/field` → `doc/field`) para mostrar de dónde viene. */
export const fieldLabel = (hit: Pick<FieldRankHit, "name" | "field">): string => `${hit.name}/${hit.field}`;

/**
 * Texto para el estado que NO es un resultado. `null` cuando sí lo es: la vista decide qué
 * hacer con `ok` (incluida la lista vacía, que significa "sin parecidos").
 */
export function similarityNotice(result: SimilarityResult<unknown> | null): string | null {
  if (!result || result.status === "ok") return null;
  if (result.status === "not_indexed") return "El corpus todavía no está indexado: no hay nada con qué comparar.";
  return `Similitud no disponible: ${result.reason}.`;
}
