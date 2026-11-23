/** Cobertura de anclaje: helper puro, sin React ni red. */

export interface OffsetRange {
  start: number;
  end: number;
}

export interface Coverage {
  coveredChars: number;
  totalChars: number;
  /** Porcentaje 0-100 con un decimal. */
  pct: number;
}

/** Une rangos solapados o contiguos; descarta los inválidos y recorta a `total`. */
export function mergeRanges(ranges: OffsetRange[], total: number): OffsetRange[] {
  const valid = ranges
    .filter((r) => r.start >= 0 && r.end > r.start)
    .map((r) => ({ start: r.start, end: Math.min(r.end, total) }))
    .filter((r) => r.end > r.start)
    .sort((a, b) => a.start - b.start);
  const merged: OffsetRange[] = [];
  for (const r of valid) {
    const last = merged[merged.length - 1];
    if (last && r.start <= last.end) last.end = Math.max(last.end, r.end);
    else merged.push({ ...r });
  }
  return merged;
}

/** Fracción del cuerpo cubierta por la unión de los rangos de los átomos. */
export function computeCoverage(ranges: OffsetRange[], totalChars: number): Coverage {
  if (totalChars <= 0) return { coveredChars: 0, totalChars: 0, pct: 0 };
  const coveredChars = mergeRanges(ranges, totalChars).reduce((n, r) => n + (r.end - r.start), 0);
  return { coveredChars, totalChars, pct: Math.round((coveredChars / totalChars) * 1000) / 10 };
}
