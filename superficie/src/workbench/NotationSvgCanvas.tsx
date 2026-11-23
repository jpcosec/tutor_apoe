/**
 * Canvas SVG declarativo para diagramas resueltos por `sldb.api.notations` (`SV02`).
 * No calcula reglas de notación: dibuja los `nodes` y `links` que entrega
 * `GET /notations/view` o `segment.projection`. El único cálculo propio es la
 * disposición geométrica por niveles (`layoutNotation`), derivada solo de `view.links`.
 */
import type { NotationLink, NotationNode, ResolvedNotationView } from "../core/contract";

export interface NotationSvgCanvasProps {
  view: ResolvedNotationView;
  selectedNodeDoc?: string | null;
  onSelectNode?(node: NotationNode): void;
  compact?: boolean;
  /** Decide si una ref es AtomDoc (el inspector también mira el modelo del store). */
  isAtomRef?(ref: string): boolean;
}

export type NotationNodeType = "initial" | "terminal" | "decision" | "step";

export interface PositionedNode {
  node: NotationNode;
  type: NotationNodeType;
  level: number;
  column: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface PositionedEdge {
  link: NotationLink;
  from: PositionedNode;
  to: PositionedNode;
}

export interface NotationLayout {
  nodes: PositionedNode[];
  edges: PositionedEdge[];
  /** `element` de los nodos por nivel, en orden de columna. */
  levels: string[][];
  width: number;
  height: number;
}

const INITIAL_WORDS = ["entry", "start", "initial", "inicio"];
const TERMINAL_WORDS = ["exit", "end", "terminal", "final", "fin", "bullseye"];

function hasWord(value: string | undefined, words: string[]): boolean {
  const v = (value ?? "").toLowerCase();
  if (!v) return false;
  return v.split(/[^a-z]+/).some((part) => words.includes(part));
}

/** Clasifica un nodo solo con lo que declara (`function`, `shape`, `glyph`, `kind`). */
export function classifyNode(node: NotationNode): NotationNodeType {
  const fn = node.function;
  if (hasWord(fn, INITIAL_WORDS) || node.shape === "circle" || hasWord(node.glyph, ["initial", "start"])) {
    return "initial";
  }
  if (
    hasWord(fn, TERMINAL_WORDS) ||
    hasWord(node.shape, TERMINAL_WORDS) ||
    hasWord(node.glyph, ["final", "terminal", "end"])
  ) {
    return "terminal";
  }
  if (node.shape === "diamond" || fn === "decision" || node.kind === "decision") return "decision";
  return "step";
}

/** Una ref de AtomDoc se reconoce por prefijo `AtomDoc:`. */
export function isAtomDocRef(ref: string): boolean {
  return ref.startsWith("AtomDoc:");
}

function cleanLabel(node: NotationNode): string {
  return (node.label || node.title || node.element).replace(/\n/g, " ");
}

/** Disposición por niveles (camino más largo desde las raíces) a partir de `view.links` reales. */
export function layoutNotation(view: ResolvedNotationView, compact = false): NotationLayout {
  const nodes = view.nodes ?? [];
  const links = view.links ?? [];
  const boxW = compact ? 150 : 170;
  const boxH = compact ? 40 : 46;
  const decW = compact ? 150 : 180;
  const decH = compact ? 70 : 84;
  const gapX = compact ? 28 : 44;
  const gapY = compact ? 46 : 62;
  const pad = 36;
  const topPad = 52; // espacio para el badge del nodo seleccionado

  const keyOf = new Map<string, string>();
  for (const n of nodes) {
    keyOf.set(n.element, n.doc);
    keyOf.set(n.doc, n.doc);
  }
  const outs = new Map<string, string[]>();
  const hasLink = new Set<string>();
  const incoming = new Set<string>();
  const real: { link: NotationLink; s: string; t: string }[] = [];
  for (const link of links) {
    const s = keyOf.get(link.source);
    const t = keyOf.get(link.target);
    if (!s || !t) continue;
    real.push({ link, s, t });
    hasLink.add(s);
    hasLink.add(t);
    if (s !== t) {
      incoming.add(t);
      outs.set(s, [...(outs.get(s) ?? []), t]);
    }
  }

  // Niveles: DFS desde raíces ignorando aristas de retroceso (ciclos), luego camino más largo.
  const linked = nodes.filter((n) => hasLink.has(n.doc));
  const roots = linked.filter((n) => !incoming.has(n.doc));
  const starts = roots.length > 0 ? roots : linked.slice(0, 1);
  const state = new Map<string, 0 | 1 | 2>();
  const forward = new Map<string, string[]>();
  const visit = (id: string) => {
    state.set(id, 1);
    for (const t of outs.get(id) ?? []) {
      if (state.get(t) === 1) continue; // retroceso
      forward.set(id, [...(forward.get(id) ?? []), t]);
      if (!state.has(t)) visit(t);
    }
    state.set(id, 2);
  };
  for (const r of starts) if (!state.has(r.doc)) visit(r.doc);
  for (const n of linked) if (!state.has(n.doc)) visit(n.doc);

  const levelOf = new Map<string, number>();
  const assign = (id: string, lv: number) => {
    if ((levelOf.get(id) ?? -1) >= lv) return;
    levelOf.set(id, lv);
    for (const t of forward.get(id) ?? []) assign(t, lv + 1);
  };
  for (const r of starts) assign(r.doc, 0);
  for (const n of linked) if (!levelOf.has(n.doc)) assign(n.doc, 0);

  const grouped: NotationNode[][] = [];
  for (const n of linked) {
    const lv = levelOf.get(n.doc) ?? 0;
    (grouped[lv] ??= []).push(n);
  }
  // Nodos sin ningún enlace: su propio nivel final, no se descartan.
  const loose = nodes.filter((n) => !hasLink.has(n.doc));
  const levelsNodes: NotationNode[][] = grouped.filter(Boolean);
  if (loose.length > 0) levelsNodes.push(loose);

  const sizeOf = (type: NotationNodeType) =>
    type === "decision"
      ? { w: decW, h: decH }
      : type === "step"
        ? { w: boxW, h: boxH }
        : { w: boxW, h: 28 };

  const rows = levelsNodes.map((row) =>
    row.map((node) => {
      const type = classifyNode(node);
      return { node, type, ...sizeOf(type) };
    }),
  );
  const rowWidths = rows.map((r) => r.reduce((a, c) => a + c.w, 0) + gapX * Math.max(0, r.length - 1));
  const innerW = Math.max(0, ...rowWidths);
  const width = Math.max(innerW + pad * 2, 360);

  const positioned: PositionedNode[] = [];
  let y = topPad;
  rows.forEach((row, level) => {
    const rowH = Math.max(...row.map((c) => c.h));
    let x = (width - rowWidths[level]!) / 2;
    row.forEach((c, column) => {
      positioned.push({ node: c.node, type: c.type, level, column, x, y: y + (rowH - c.h) / 2, w: c.w, h: c.h });
      x += c.w + gapX;
    });
    y += rowH + gapY;
  });
  const height = rows.length === 0 ? 0 : y - gapY + pad;

  const byDoc = new Map(positioned.map((p) => [p.node.doc, p]));
  const edges: PositionedEdge[] = [];
  for (const { link, s, t } of real) {
    const from = byDoc.get(s);
    const to = byDoc.get(t);
    if (from && to) edges.push({ link, from, to });
  }

  return {
    nodes: positioned,
    edges,
    levels: levelsNodes.map((row) => row.map((n) => n.element)),
    width,
    height,
  };
}

function edgePath(from: PositionedNode, to: PositionedNode): { d: string; mx: number; my: number } {
  const forward = to.level > from.level;
  if (forward) {
    const x1 = from.x + from.w / 2;
    const y1 = from.y + from.h;
    const x2 = to.x + to.w / 2;
    const y2 = to.y;
    const c = (y2 - y1) / 2;
    return { d: `M ${x1} ${y1} C ${x1} ${y1 + c}, ${x2} ${y2 - c}, ${x2} ${y2}`, mx: (x1 + x2) / 2, my: (y1 + y2) / 2 };
  }
  // Mismo nivel o retroceso: rodea por el costado derecho.
  const x1 = from.x + from.w;
  const y1 = from.y + from.h / 2;
  const x2 = to.x + to.w;
  const y2 = to.y + to.h / 2;
  const out = Math.max(x1, x2) + 34;
  return { d: `M ${x1} ${y1} C ${out} ${y1}, ${out} ${y2}, ${x2} ${y2}`, mx: out, my: (y1 + y2) / 2 };
}

const INK = "var(--wb-ink)";
const MUTED = "var(--wb-ink-muted)";

/** Parte una etiqueta en hasta `maxLines` líneas de `maxChars`; la última termina en "…" si sobra texto. */
export function wrapLabel(label: string, maxChars: number, maxLines = 2): string[] {
  const words = label.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length <= maxChars) {
      current = next;
      continue;
    }
    if (current) lines.push(current);
    current = word;
  }
  if (current) lines.push(current);
  const hard = lines.flatMap((l) => {
    const parts: string[] = [];
    for (let i = 0; i < l.length; i += maxChars) parts.push(l.slice(i, i + maxChars));
    return parts;
  });
  if (hard.length <= maxLines) return hard;
  const kept = hard.slice(0, maxLines);
  const last = kept[maxLines - 1]!;
  kept[maxLines - 1] = `${last.slice(0, Math.max(0, maxChars - 1))}…`;
  return kept;
}

const CHAR_W = 6.6;

/** Texto multilínea centrado verticalmente en `cy`. */
function LabelText({
  lines,
  x,
  cy,
  anchor,
  weight,
}: {
  lines: string[];
  x: number;
  cy: number;
  anchor: "start" | "middle";
  weight: number;
}) {
  const lineH = 13;
  const top = cy + 4 - ((lines.length - 1) * lineH) / 2;
  return (
    <text x={x} y={top} textAnchor={anchor} fontFamily="JetBrains Mono, monospace" fontSize="11" fontWeight={weight} fill={INK}>
      {lines.map((line, i) => (
        <tspan key={i} x={x} dy={i === 0 ? 0 : lineH}>
          {line}
        </tspan>
      ))}
    </text>
  );
}

export function NotationSvgCanvas({
  view,
  selectedNodeDoc,
  onSelectNode,
  compact = false,
  isAtomRef = isAtomDocRef,
}: NotationSvgCanvasProps) {
  const nodes = view.nodes ?? [];
  if (nodes.length === 0) {
    return <div className="wb-chip">Diagrama sin nodos resueltos en el store.</div>;
  }
  const layout = layoutNotation(view, compact);

  return (
    <svg
      viewBox={`0 0 ${layout.width} ${layout.height}`}
      // Compacto (bloque embebido): se ajusta al ancho. Inspector: tamaño natural y el lienzo hace scroll.
      style={
        compact
          ? { width: "100%", maxHeight: "280px", display: "block" }
          : { width: layout.width, height: layout.height, flex: "none", display: "block", margin: "auto" }
      }
      role="img"
      aria-label={view.title || view.spec}
      data-testid="notation-svg"
    >
      <defs>
        <marker id="wb-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1 L 8 5 L 0 9 z" fill="#1A1A1A" />
        </marker>
      </defs>

      {layout.edges.map(({ link, from, to }, i) => {
        const { d, mx, my } = edgePath(from, to);
        const label = link.label;
        return (
          <g key={`${link.source}-${link.target}-${i}`} data-testid="notation-edge">
            <path d={d} fill="none" stroke={INK} strokeWidth="1.1" markerEnd="url(#wb-arrow)" />
            {label && (
              <g>
                <rect x={mx - label.length * 3.2 - 5} y={my - 8} width={label.length * 6.4 + 10} height={16} fill="var(--wb-paper)" stroke="var(--wb-hairline)" />
                <text x={mx} y={my + 3.5} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="10" fill={INK}>
                  {label}
                </text>
              </g>
            )}
          </g>
        );
      })}

      {layout.nodes.map(({ node, type, x, y, w, h }) => {
        const isSelected = selectedNodeDoc === node.doc || selectedNodeDoc === node.element;
        const cx = x + w / 2;
        const cy = y + h / 2;
        const stroke = isSelected ? INK : MUTED;
        const strokeWidth = isSelected ? 1.8 : 1.1;
        const label = cleanLabel(node);
        const atoms = node.refs.filter(isAtomRef).length;
        const others = node.refs.length - atoms;
        const badge = `SpecNodeDoc: .${node.element.split(".").pop()} · ${atoms} atoms · ${others} ref`;

        return (
          <g
            key={node.doc}
            onClick={() => onSelectNode?.(node)}
            style={{ cursor: onSelectNode ? "pointer" : "default" }}
            data-testid={`diagram-node-${node.element}`}
            data-node-type={type}
          >
            <title>{label}</title>
            {(type === "initial" || type === "terminal") && (
              // Zona de clic de todo el slot: el círculo y el rótulo solos dejan huecos sin evento.
              <rect x={x} y={y} width={w} height={h} fill="transparent" />
            )}
            {type === "initial" && (
              <>
                <circle cx={cx - w / 2 + 10} cy={cy} r={7} fill={INK} stroke={stroke} strokeWidth={strokeWidth} />
                <LabelText lines={wrapLabel(label, Math.floor((w - 30) / CHAR_W))} x={cx - w / 2 + 24} cy={cy} anchor="start" weight={isSelected ? 600 : 500} />
              </>
            )}
            {type === "terminal" && (
              <>
                <circle cx={cx - w / 2 + 10} cy={cy} r={9} fill="var(--wb-card)" stroke={INK} strokeWidth={strokeWidth} />
                <circle cx={cx - w / 2 + 10} cy={cy} r={4.5} fill={INK} />
                <LabelText lines={wrapLabel(label, Math.floor((w - 32) / CHAR_W))} x={cx - w / 2 + 26} cy={cy} anchor="start" weight={isSelected ? 600 : 500} />
              </>
            )}
            {type === "decision" && (
              <>
                <polygon
                  points={`${cx},${y} ${x + w},${cy} ${cx},${y + h} ${x},${cy}`}
                  fill="var(--wb-card)"
                  stroke={stroke}
                  strokeWidth={strokeWidth}
                />
                <LabelText lines={wrapLabel(label, Math.floor((w * 0.62) / CHAR_W))} x={cx} cy={cy} anchor="middle" weight={600} />
              </>
            )}
            {type === "step" && (
              <>
                <rect x={x} y={y} width={w} height={h} rx={2} fill="var(--wb-card)" stroke={stroke} strokeWidth={strokeWidth} />
                <LabelText lines={wrapLabel(label, Math.floor((w - 14) / CHAR_W))} x={cx} cy={cy} anchor="middle" weight={isSelected ? 600 : 500} />
              </>
            )}
            {isSelected && type === "decision" && (
              <g data-testid="node-badge">
                <rect x={cx - badge.length * 3.1 - 8} y={y - 28} width={badge.length * 6.2 + 16} height={20} fill={INK} />
                <text x={cx} y={y - 14} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="10" fill="var(--wb-paper)">
                  {badge}
                </text>
              </g>
            )}
          </g>
        );
      })}
    </svg>
  );
}
