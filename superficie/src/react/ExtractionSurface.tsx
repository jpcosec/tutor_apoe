/**
 * Texto crudo con los atoms que SLDB extrae de él: cada field pintado con su color,
 * los tramos que no salen de ningún field ni del template quedan rayados.
 */
import type { ExtractionSegments } from "../core/contract";
import { FieldColors } from "../core/colors";

type Mark = { start: number; end: number; kind: "field" | "unmatched"; path?: string; approximate?: boolean };

function marksOf(result: ExtractionSegments): Mark[] {
  const fields: Mark[] = result.fields
    .filter((f) => f.end > f.start)
    .map((f) => ({ start: f.start, end: f.end, kind: "field", path: f.path, approximate: f.alignment === "approximate" }));
  const unmatched: Mark[] = result.unmatched.map((u) => ({ start: u.start, end: u.end, kind: "unmatched" }));
  return [...fields, ...unmatched].sort((a, b) => a.start - b.start || b.end - a.end);
}

export function ExtractionSurface({ result, colors, highlight }: { result: ExtractionSegments; colors: FieldColors; highlight: string | null }) {
  const out: JSX.Element[] = [];
  let cursor = 0;
  for (const mark of marksOf(result)) {
    if (mark.start < cursor) continue;
    if (mark.start > cursor) out.push(<span key={`t${cursor}`}>{result.text.slice(cursor, mark.start)}</span>);
    const text = result.text.slice(mark.start, mark.end);
    if (mark.kind === "unmatched") {
      out.push(
        <mark key={`u${mark.start}`} className="unmatched" title="No sale de ningún field ni del template">
          {text}
        </mark>,
      );
    } else {
      const key = FieldColors.keyFor(mark.path ?? "");
      const dimmed = highlight && highlight !== key;
      out.push(
        <mark
          key={`f${mark.start}`}
          className={`extracted f-${colors.slotOf(key)}${mark.approximate ? " is-approximate" : ""}${dimmed ? " is-dimmed" : ""}`}
          title={`${mark.path}${mark.approximate ? " (alineación aproximada)" : ""}`}
        >
          {text}
        </mark>,
      );
    }
    cursor = mark.end;
  }
  if (cursor < result.text.length) out.push(<span key="tail">{result.text.slice(cursor)}</span>);
  return <pre className="extraction">{out}</pre>;
}
