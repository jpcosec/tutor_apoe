/**
 * ÁTOMOS EN EL TEXTO · lógica pura (sin DOM): párrafos, segmentación por bordes de átomo y
 * conversión selección → offsets globales del `body`.
 *
 * Los offsets siempre son índices UTF-16 del `body` completo (los mismos que guarda un
 * `AtomDoc.start/end`). El separador "\n\n" entre párrafos no pertenece a ningún párrafo:
 * ningún segmento lo contiene, así un rango que lo cruza se parte en un tramo por párrafo.
 */
import { anchorState } from "./atoms";
import type { Atom } from "./contract";

export interface Paragraph {
  start: number;
  end: number;
  text: string;
}

export interface EffectiveRange {
  id: string;
  start: number;
  end: number;
}

export interface TextSegment {
  start: number;
  end: number;
  text: string;
  /** Átomos que cubren todo el segmento, en el orden de `ranges`. Vacío = texto sin subrayar. */
  atomIds: string[];
}

export interface ParagraphSegments extends Paragraph {
  segments: TextSegment[];
}

/** Párrafos separados por "\n\n". Los vacíos (más de dos saltos seguidos) se omiten. */
export function paragraphsOf(body: string): Paragraph[] {
  const out: Paragraph[] = [];
  let pos = 0;
  for (const text of body.split("\n\n")) {
    if (text.length > 0) out.push({ start: pos, end: pos + text.length, text });
    pos += text.length + 2;
  }
  return out;
}

/**
 * Rango con el que se subraya un átomo: intacto → el guardado; movido → donde está la cita
 * ahora; huérfano (o rango vacío/inválido) → `null`, no se subraya.
 */
export function effectiveRange(body: string, atom: Pick<Atom, "id" | "start" | "end" | "quote">): EffectiveRange | null {
  const check = anchorState(body, atom);
  if (check.state === "orphan") return null;
  const start = check.state === "drifted" && check.movedTo !== undefined ? check.movedTo : atom.start;
  const end = check.state === "drifted" ? start + atom.quote.length : atom.end;
  return end > start ? { id: atom.id, start, end } : null;
}

/** Corta cada párrafo en todos los bordes de `ranges` (recortados al párrafo). */
export function segmentBody(body: string, ranges: EffectiveRange[]): ParagraphSegments[] {
  return paragraphsOf(body).map((p) => {
    const inside = ranges.filter((r) => r.end > p.start && r.start < p.end);
    const cuts = new Set<number>([p.start, p.end]);
    for (const r of inside) {
      cuts.add(Math.max(r.start, p.start));
      cuts.add(Math.min(r.end, p.end));
    }
    const points = [...cuts].sort((a, b) => a - b);
    const segments: TextSegment[] = [];
    for (let i = 0; i + 1 < points.length; i++) {
      const start = points[i]!;
      const end = points[i + 1]!;
      segments.push({
        start,
        end,
        text: body.slice(start, end),
        atomIds: inside.filter((r) => r.start <= start && r.end >= end).map((r) => r.id),
      });
    }
    return { ...p, segments };
  });
}

export type SelectionCheck = { ok: true; from: number; to: number } | { ok: false; reason: string };

/**
 * Valida una selección `[from, to)` del `body` para crear un átomo: no vacía (ni solo espacios)
 * y dentro de un único párrafo.
 */
export function checkSelection(body: string, from: number, to: number): SelectionCheck {
  const a = Math.max(0, Math.min(from, to));
  const b = Math.min(body.length, Math.max(from, to));
  if (b <= a || body.slice(a, b).trim() === "") return { ok: false, reason: "La selección está vacía." };
  const paragraphs = paragraphsOf(body);
  const first = paragraphs.find((p) => a >= p.start && a < p.end);
  const last = paragraphs.find((p) => b > p.start && b <= p.end);
  if (!first || !last || first !== last) return { ok: false, reason: "La selección cruza un límite de párrafo; elige texto de un solo párrafo." };
  return { ok: true, from: a, to: b };
}

/** Punto de un Range ya resuelto a un segmento: `segmentStart` (data-start) + desplazamiento en su texto. */
export function pointOffset(segmentStart: number, offsetInSegment: number): number {
  return segmentStart + offsetInSegment;
}
