/**
 * Convierte la secuencia de segmentos en unidades que una superficie sabe dibujar:
 * frontmatter como propiedades, líneas Markdown con fields inline, y bloques.
 *
 * Trabaja solo con los textos de los segmentos: no parsea Markdown completo, solo
 * clasifica cada línea por su prefijo (heading, lista, cita, código, tabla).
 */
import type { CompositionPiece, FieldSegment, Segment } from "./contract";
import { listItemOf, rootOf } from "./paths";

export type InlinePiece = { kind: "text"; text: string } | { kind: "field"; segment: FieldSegment };

export type LineKind =
  | { type: "heading"; level: number }
  | { type: "bullet"; depth: number }
  | { type: "ordered"; depth: number; number: number }
  | { type: "quote" }
  | { type: "table" }
  | { type: "code" }
  | { type: "fence" }
  | { type: "paragraph" };

export interface FrontmatterRow {
  key: string;
  pieces: InlinePiece[];
}

export type LayoutUnit =
  | { unit: "frontmatter"; rows: FrontmatterRow[] }
  | { unit: "line"; kind: LineKind; pieces: InlinePiece[] }
  | { unit: "list"; ordered: boolean; items: InlinePiece[][]; listPath: string | null }
  | { unit: "block"; segment: FieldSegment }
  | { unit: "piece"; segment: CompositionPiece };

export function isBlockField(segment: FieldSegment): boolean {
  return (
    segment.display === "block" ||
    segment.composition != null ||
    segment.children.some((child) => child.type === "composition")
  );
}

/** Aplana a una secuencia de piezas en la que los saltos de línea quedan como texto. */
type Token = InlinePiece | { kind: "block"; segment: FieldSegment } | { kind: "piece"; segment: CompositionPiece };

function tokenize(segments: Segment[]): Token[] {
  return segments.map((segment): Token => {
    if (segment.type === "literal") return { kind: "text", text: segment.text };
    if (segment.type === "composition") return { kind: "piece", segment };
    return isBlockField(segment) ? { kind: "block", segment } : { kind: "field", segment };
  });
}

function splitFrontmatter(tokens: Token[]): { rows: FrontmatterRow[] | null; rest: Token[] } {
  const first = tokens[0];
  if (!first || first.kind !== "text" || !first.text.startsWith("---\n")) return { rows: null, rest: tokens };
  const lines = toLines([{ kind: "text", text: first.text.slice(4) }, ...tokens.slice(1)]);
  const closing = lines.findIndex((line) => line.length === 1 && isText(line[0], "---"));
  if (closing < 0) return { rows: null, rest: tokens };
  const rows = lines.slice(0, closing).map(toFrontmatterRow).filter((row): row is FrontmatterRow => row !== null);
  return { rows, rest: lines.slice(closing + 1).flatMap((line, i) => (i === 0 ? line : [newline(), ...line])) };
}

function newline(): Token {
  return { kind: "text", text: "\n" };
}

function isText(token: Token | undefined, text: string): boolean {
  return token?.kind === "text" && token.text.trim() === text;
}

function toFrontmatterRow(line: Token[]): FrontmatterRow | null {
  const [head, ...rest] = line;
  if (!head || head.kind !== "text") return null;
  const match = /^\s*([A-Za-z0-9_-]+)\s*:\s?(.*)$/s.exec(head.text);
  if (!match || !match[1]) return null;
  const pieces: InlinePiece[] = [];
  if (match[2]) pieces.push({ kind: "text", text: match[2] });
  for (const token of rest) if (token.kind === "text" || token.kind === "field") pieces.push(token);
  return { key: match[1], pieces };
}

/** Parte los tokens por `\n`; los bloques quedan como línea propia. */
function toLines(tokens: Token[]): Token[][] {
  const lines: Token[][] = [[]];
  const current = () => lines[lines.length - 1] as Token[];
  for (const token of tokens) {
    if (token.kind !== "text") {
      if (token.kind !== "field" && current().length > 0) lines.push([]);
      current().push(token);
      if (token.kind !== "field") lines.push([]);
      continue;
    }
    const parts = token.text.split("\n");
    parts.forEach((part, index) => {
      if (index > 0) lines.push([]);
      if (part.length > 0) current().push({ kind: "text", text: part });
    });
  }
  return lines;
}

const LINE_PATTERNS: [RegExp, (m: RegExpExecArray) => LineKind][] = [
  [/^(#{1,6})\s+/, (m) => ({ type: "heading", level: (m[1] ?? "#").length })],
  [/^(\s*)[-*+]\s+/, (m) => ({ type: "bullet", depth: Math.floor((m[1] ?? "").length / 2) })],
  [/^(\s*)(\d+)[.)]\s+/, (m) => ({ type: "ordered", depth: Math.floor((m[1] ?? "").length / 2), number: Number(m[2]) })],
  [/^>\s?/, () => ({ type: "quote" })],
];

function classify(pieces: InlinePiece[], inCode: boolean): { kind: LineKind; pieces: InlinePiece[] } {
  const head = pieces[0];
  const text = head?.kind === "text" ? head.text : "";
  if (/^\s*(```|~~~)/.test(text)) return { kind: { type: "fence" }, pieces };
  if (inCode) return { kind: { type: "code" }, pieces };
  if (/^\s*\|/.test(text)) return { kind: { type: "table" }, pieces };
  for (const [pattern, build] of LINE_PATTERNS) {
    const match = pattern.exec(text);
    if (!match) continue;
    const stripped = text.slice(match[0].length);
    const rest = pieces.slice(1);
    return { kind: build(match), pieces: stripped ? [{ kind: "text", text: stripped }, ...rest] : rest };
  }
  return { kind: { type: "paragraph" }, pieces };
}

/** Si todos los fields de los ítems son `lista/i` de la misma lista, devuelve esa lista. */
function listPathOf(items: InlinePiece[][]): string | null {
  const roots = new Set<string>();
  for (const item of items) {
    for (const piece of item) {
      if (piece.kind !== "field") continue;
      const listItem = listItemOf(piece.segment.path);
      roots.add(listItem ? listItem.list : isEmptyList(piece.segment) ? piece.segment.path : "");
    }
  }
  const [only] = [...roots];
  return roots.size === 1 && only ? only : null;
}

function isEmptyList(segment: FieldSegment): boolean {
  return segment.start === segment.end && (segment.kind === "stringlist" || segment.kind === "enumlist");
}

function pushLine(units: LayoutUnit[], kind: LineKind, pieces: InlinePiece[]): void {
  const isList = kind.type === "bullet" || kind.type === "ordered";
  const previous = units[units.length - 1];
  if (isList && previous?.unit === "list" && previous.ordered === (kind.type === "ordered")) {
    previous.items.push(pieces);
    previous.listPath = listPathOf(previous.items);
    return;
  }
  if (isList) {
    units.push({ unit: "list", ordered: kind.type === "ordered", items: [pieces], listPath: listPathOf([pieces]) });
    return;
  }
  units.push({ unit: "line", kind, pieces });
}

function isBlankLine(line: Token[]): boolean {
  return line.every((token) => token.kind === "text" && token.text.trim() === "");
}

export function layoutSegments(segments: Segment[]): LayoutUnit[] {
  const { rows, rest } = splitFrontmatter(tokenize(segments));
  const units: LayoutUnit[] = rows ? [{ unit: "frontmatter", rows }] : [];
  let inCode = false;
  for (const line of toLines(rest)) {
    const only = line[0];
    if (line.length === 1 && only && (only.kind === "block" || only.kind === "piece")) {
      units.push(only.kind === "block" ? { unit: "block", segment: only.segment } : { unit: "piece", segment: only.segment });
      continue;
    }
    if (isBlankLine(line) && !line.some((t) => t.kind === "field")) {
      if (inCode) units.push({ unit: "line", kind: { type: "code" }, pieces: [] });
      continue;
    }
    const { kind, pieces } = classify(line as InlinePiece[], inCode);
    if (kind.type === "fence") inCode = !inCode;
    pushLine(units, kind, pieces);
  }
  return units;
}

/** Todos los fields de nivel superior (sin entrar a piezas compuestas), en orden. */
export function topLevelFields(segments: Segment[]): FieldSegment[] {
  return segments.filter((s): s is FieldSegment => s.type === "field");
}

/** Raíces de field en orden de aparición: base de la leyenda y de los colores. */
export function fieldRoots(segments: Segment[]): string[] {
  const seen: string[] = [];
  for (const field of topLevelFields(segments)) {
    const root = rootOf(field.path);
    if (!seen.includes(root)) seen.push(root);
  }
  return seen;
}
