/**
 * GRAFO DE ÁTOMOS · lógica pura de la vista (sin DOM ni red).
 *
 * - Regiones: un rectángulo por grupo (primer segmento del primer tag), grilla de átomos adentro.
 * - Plegado: un grupo plegado es UN nodo (`group:<grupo>`) que fusiona las aristas de sus átomos.
 * - Aristas: solo entre átomos. `relation` (RelationDoc) se dibuja con etiqueta; `reference`
 *   (estructurales) tenue y sin etiqueta; `inherited` (extremo-grupo proyectado) punteada.
 * - Geometría: recorte de línea a la caja, carriles para aristas paralelas, hit-testing, zoom.
 */
import { atomRelationTypes, groupTree, inGroup, inheritedEdges, type GroupNode } from "./atoms";
import type { Atom, Edge, GraphDocument, Payload, RelationTypeSpec } from "./contract";

export const NO_GROUP = "(sin grupo)";
export const GROUP_KEY_PREFIX = "group:";

// ---------------------------------------------------------------- grupos

/** Grupo principal: primer segmento (antes del primer punto) del primer tag. */
export function primaryGroup(atom: Pick<Atom, "tags">): string {
  const first = atom.tags.find((t) => t.split(".").some(Boolean));
  if (!first) return NO_GROUP;
  return first.split(".").filter(Boolean)[0]!;
}

/** Clave de nodo de un átomo: su gid, o la del grupo si está plegado. */
export function nodeKeyOf(atom: Atom, collapsed: ReadonlySet<string>): string {
  const g = primaryGroup(atom);
  return collapsed.has(g) ? `${GROUP_KEY_PREFIX}${g}` : atom.gid;
}

export const isGroupKey = (key: string): boolean => key.startsWith(GROUP_KEY_PREFIX);
export const groupOfKey = (key: string): string => key.slice(GROUP_KEY_PREFIX.length);

/** Gids de los átomos resaltados al elegir un tag/grupo (prefijo) en la barra. */
export function highlightAtoms(atoms: Atom[], tag: string | null): Set<string> {
  if (tag === null) return new Set();
  if (tag === NO_GROUP) return new Set(atoms.filter((a) => a.tags.length === 0).map((a) => a.gid));
  return new Set(atoms.filter((a) => inGroup(a, tag)).map((a) => a.gid));
}

/** Claves de nodo a resaltar (los átomos de un grupo plegado resaltan su nodo-grupo). */
export function highlightKeys(atoms: Atom[], tag: string | null, collapsed: ReadonlySet<string>): Set<string> {
  const gids = highlightAtoms(atoms, tag);
  return new Set(atoms.filter((a) => gids.has(a.gid)).map((a) => nodeKeyOf(a, collapsed)));
}

export function flattenGroups(tree: GroupNode[]): GroupNode[] {
  return tree.flatMap((n) => [n, ...flattenGroups(n.children)]);
}

// ---------------------------------------------------------------- layout

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface LayoutOptions {
  nodeW: number;
  nodeH: number;
  gap: number;
  pad: number;
  headerH: number;
  regionGap: number;
  /** Ancho a partir del cual las regiones saltan a la fila siguiente. */
  maxWidth: number;
  maxCols: number;
}

export const DEFAULT_LAYOUT: LayoutOptions = { nodeW: 152, nodeH: 58, gap: 14, pad: 14, headerH: 30, regionGap: 28, maxWidth: 1000, maxCols: 4 };

export interface LayoutNode extends Box {
  key: string;
  kind: "atom" | "group";
  /** Solo para átomos. */
  atomId?: string;
  group: string;
  /** Solo para nodos-grupo: cuántos átomos fusiona. */
  count?: number;
}

export interface LayoutRegion extends Box {
  group: string;
  count: number;
  collapsed: boolean;
  nodeKeys: string[];
}

export interface GraphLayout {
  regions: LayoutRegion[];
  nodes: LayoutNode[];
  byKey: Record<string, LayoutNode>;
  width: number;
  height: number;
}

/**
 * Layout determinista: regiones ordenadas por nombre (sin grupo al final), empaquetadas en
 * filas de izquierda a derecha; dentro, grilla de `ceil(sqrt(n))` columnas (tope `maxCols`).
 * Los átomos plegados de una región se reemplazan por un único nodo-grupo.
 * Los átomos de entrada deben ser los visibles (sin descartados).
 */
export function layoutRegions(atoms: Atom[], collapsed: ReadonlySet<string> = new Set(), options: Partial<LayoutOptions> = {}): GraphLayout {
  const o = { ...DEFAULT_LAYOUT, ...options };
  const byGroup = new Map<string, Atom[]>();
  for (const atom of atoms) {
    const g = primaryGroup(atom);
    byGroup.set(g, [...(byGroup.get(g) ?? []), atom]);
  }
  const names = [...byGroup.keys()].sort((a, b) => (a === NO_GROUP ? 1 : b === NO_GROUP ? -1 : a.localeCompare(b)));

  const regions: LayoutRegion[] = [];
  const nodes: LayoutNode[] = [];
  let cx = 0;
  let cy = 0;
  let rowH = 0;
  let width = 0;

  for (const group of names) {
    const members = byGroup.get(group)!;
    const isCollapsed = collapsed.has(group);
    const slots = isCollapsed ? 1 : members.length;
    const cols = Math.max(1, Math.min(o.maxCols, Math.ceil(Math.sqrt(slots))));
    const rows = Math.ceil(slots / cols);
    const w = o.pad * 2 + cols * o.nodeW + (cols - 1) * o.gap;
    const h = o.headerH + o.pad + rows * o.nodeH + (rows - 1) * o.gap + o.pad;
    if (cx > 0 && cx + w > o.maxWidth) {
      cx = 0;
      cy += rowH + o.regionGap;
      rowH = 0;
    }
    const region: LayoutRegion = { group, x: cx, y: cy, w, h, count: members.length, collapsed: isCollapsed, nodeKeys: [] };
    const place = (i: number, node: Omit<LayoutNode, keyof Box>) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const n: LayoutNode = {
        ...node,
        x: cx + o.pad + col * (o.nodeW + o.gap),
        y: cy + o.headerH + o.pad + row * (o.nodeH + o.gap),
        w: o.nodeW,
        h: o.nodeH,
      };
      nodes.push(n);
      region.nodeKeys.push(n.key);
    };
    if (isCollapsed) place(0, { key: `${GROUP_KEY_PREFIX}${group}`, kind: "group", group, count: members.length });
    else members.forEach((a, i) => place(i, { key: a.gid, kind: "atom", atomId: a.id, group }));
    regions.push(region);
    cx += w + o.regionGap;
    rowH = Math.max(rowH, h);
    width = Math.max(width, region.x + w);
  }
  const byKey = Object.fromEntries(nodes.map((n) => [n.key, n]));
  return { regions, nodes, byKey, width, height: regions.length ? cy + rowH : 0 };
}

/** ¿Se solapan dos cajas? (tocarse por el borde no cuenta). */
export function boxesOverlap(a: Box, b: Box): boolean {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

// ---------------------------------------------------------------- aristas

export type LinkKind = "relation" | "reference";

/** Arista entre dos átomos (antes de plegar). */
export interface AtomLink {
  edge: Edge;
  /** gids de átomo. */
  source: string;
  target: string;
  kind: LinkKind;
  inherited: boolean;
  /** Grupo del que se hereda, si `inherited`. */
  via?: string;
}

/** `relation` (RelationDoc) vs estructural: el backend real manda `origin: "relation_doc"` (el fixture usa "relation"); vale cualquiera. */
export function linkKind(edge: Edge): LinkKind {
  return edge.origin.startsWith("relation") || edge.relationDoc !== null ? "relation" : "reference";
}

/**
 * Aristas átomo→átomo: las directas y las heredadas (extremo-grupo, `GrupoDoc:<slug>` o formatos
 * viejos, proyectado con `inheritedEdges` sobre cada grupo del árbol: cada átomo del grupo y de
 * sus subgrupos la hereda). Extremos que no son átomos ni grupos (actas, informes) se ignoran:
 * no hay nodo donde dibujarlos.
 */
export function atomLinks(edges: Edge[], atoms: Atom[]): AtomLink[] {
  const gids = new Set(atoms.map((a) => a.gid));
  const out: AtomLink[] = [];
  const seen = new Set<string>();
  const direct = new Set<string>();
  const push = (link: AtomLink) => {
    if (link.source === link.target) return;
    const k = `${link.edge.id}|${link.source}|${link.target}`;
    if (seen.has(k)) return;
    // Una heredada que coincide con una directa (mismo par y tipo) sería ruido.
    const same = `${link.source}|${link.target}|${link.edge.type}`;
    if (link.inherited && direct.has(same)) return;
    if (!link.inherited) direct.add(same);
    seen.add(k);
    out.push(link);
  };
  for (const edge of edges) {
    if (gids.has(edge.source) && gids.has(edge.target)) push({ edge, source: edge.source, target: edge.target, kind: linkKind(edge), inherited: false });
  }
  for (const group of flattenGroups(groupTree(atoms))) {
    for (const ie of inheritedEdges(edges, group.id, atoms)) {
      if (!gids.has(ie.source) || !gids.has(ie.target)) continue;
      push({ edge: ie.edge, source: ie.source, target: ie.target, kind: linkKind(ie.edge), inherited: true, via: group.id });
    }
  }
  return out;
}

/** Arista dibujable: extremos son claves de nodo (átomo o grupo plegado). */
export interface GraphEdge {
  key: string;
  source: string;
  target: string;
  type: string;
  kind: LinkKind;
  inherited: boolean;
  /** Cuántas aristas originales fusiona (>1 solo con grupos plegados o duplicados). */
  count: number;
  /** Ids de las aristas originales. */
  edgeIds: string[];
  /** Ids de RelationDoc que las respaldan. */
  relationDocs: string[];
  /** Pares (atom gid → atom gid) originales, para el inspector. */
  links: AtomLink[];
}

/** Proyecta las aristas sobre los nodos visibles: plegar fusiona; las internas a un grupo plegado desaparecen. */
export function fuseLinks(links: AtomLink[], atoms: Atom[], collapsed: ReadonlySet<string>): GraphEdge[] {
  const keyOf = new Map(atoms.map((a) => [a.gid, nodeKeyOf(a, collapsed)]));
  const fused = new Map<string, GraphEdge>();
  for (const link of links) {
    const source = keyOf.get(link.source);
    const target = keyOf.get(link.target);
    if (!source || !target || source === target) continue;
    const type = link.edge.type;
    const key = `${source}|${type}|${target}|${link.kind}|${link.inherited ? "h" : "d"}`;
    const cur = fused.get(key);
    if (cur) {
      cur.count += 1;
      if (!cur.edgeIds.includes(link.edge.id)) cur.edgeIds.push(link.edge.id);
      if (link.edge.relationDoc && !cur.relationDocs.includes(link.edge.relationDoc)) cur.relationDocs.push(link.edge.relationDoc);
      cur.links.push(link);
    } else {
      fused.set(key, {
        key,
        source,
        target,
        type,
        kind: link.kind,
        inherited: link.inherited,
        count: 1,
        edgeIds: [link.edge.id],
        relationDocs: link.edge.relationDoc ? [link.edge.relationDoc] : [],
        links: [link],
      });
    }
  }
  return [...fused.values()];
}

/** Filtro por tipo (`hiddenTypes`) y por referencias (`showReferences`). */
export function filterEdges(edges: GraphEdge[], hiddenTypes: ReadonlySet<string>, showReferences: boolean): GraphEdge[] {
  return edges.filter((e) => (e.kind === "reference" ? showReferences : !hiddenTypes.has(e.type)));
}

/** Tipos de relación con al menos una arista `relation`, unidos a los declarados. */
export function relationTypeNames(declared: RelationTypeSpec[], edges: Edge[]): string[] {
  const names = new Set(atomRelationTypes(declared).map((t) => t.name));
  for (const e of edges) if (linkKind(e) === "relation") names.add(e.type);
  return [...names].sort((a, b) => a.localeCompare(b));
}

// ---------------------------------------------------------------- geometría

export interface Point {
  x: number;
  y: number;
}

export const center = (b: Box): Point => ({ x: b.x + b.w / 2, y: b.y + b.h / 2 });

/** Punto donde el rayo centro→`toward` sale de la caja. */
export function clipToBox(b: Box, toward: Point): Point {
  const c = center(b);
  const dx = toward.x - c.x;
  const dy = toward.y - c.y;
  if (dx === 0 && dy === 0) return c;
  const t = Math.min(dx === 0 ? Infinity : b.w / 2 / Math.abs(dx), dy === 0 ? Infinity : b.h / 2 / Math.abs(dy));
  return { x: c.x + dx * t, y: c.y + dy * t };
}

/**
 * Carril de cada arista entre el mismo par (sin importar el sentido): 0 para una sola,
 * ..., -1, 0, 1 centrados para varias. Devuelve `key → carril`.
 */
export function assignLanes(edges: Pick<GraphEdge, "key" | "source" | "target">[]): Record<string, number> {
  const groups = new Map<string, string[]>();
  for (const e of edges) {
    const pair = e.source < e.target ? `${e.source}\u0000${e.target}` : `${e.target}\u0000${e.source}`;
    groups.set(pair, [...(groups.get(pair) ?? []), e.key]);
  }
  const lanes: Record<string, number> = {};
  for (const keys of groups.values()) keys.forEach((k, i) => (lanes[k] = i - (keys.length - 1) / 2));
  return lanes;
}

export interface EdgeGeometry {
  /** `M x y Q cx cy x y` */
  d: string;
  from: Point;
  to: Point;
  /** Punto medio de la curva (etiqueta). */
  mid: Point;
}

export const LANE_GAP = 26;

/** Curva de `a` a `b` recortada a sus cajas; el carril curva hacia un lado fijo del par. */
export function edgeGeometry(a: Box, b: Box, lane = 0, aKey = "a", bKey = "b"): EdgeGeometry {
  const ca = center(a);
  const cb = center(b);
  // Normal canónica (del par ordenado) para que a→b y b→a no se superpongan.
  const [p, q] = aKey < bKey ? [ca, cb] : [cb, ca];
  const len = Math.hypot(q.x - p.x, q.y - p.y) || 1;
  const nx = -(q.y - p.y) / len;
  const ny = (q.x - p.x) / len;
  const off = lane * LANE_GAP;
  const ctrl = { x: (ca.x + cb.x) / 2 + nx * off * 2, y: (ca.y + cb.y) / 2 + ny * off * 2 };
  const from = clipToBox(a, ctrl.x === ca.x && ctrl.y === ca.y ? cb : ctrl);
  const to = clipToBox(b, ctrl.x === cb.x && ctrl.y === cb.y ? ca : ctrl);
  const r = (n: number) => Math.round(n * 10) / 10;
  return {
    d: `M ${r(from.x)} ${r(from.y)} Q ${r(ctrl.x)} ${r(ctrl.y)} ${r(to.x)} ${r(to.y)}`,
    from,
    to,
    mid: { x: 0.25 * from.x + 0.5 * ctrl.x + 0.25 * to.x, y: 0.25 * from.y + 0.5 * ctrl.y + 0.25 * to.y },
  };
}

/** Nodo bajo el punto `p` (coordenadas del mundo); el último dibujado gana. */
export function hitTest(nodes: Box[], p: Point): number {
  for (let i = nodes.length - 1; i >= 0; i--) {
    const b = nodes[i]!;
    if (p.x >= b.x && p.x <= b.x + b.w && p.y >= b.y && p.y <= b.y + b.h) return i;
  }
  return -1;
}

/** Clave del nodo (átomo o grupo) bajo `p`, o `null`. */
export function nodeAt(layout: GraphLayout, p: Point): string | null {
  const i = hitTest(layout.nodes, p);
  return i === -1 ? null : layout.nodes[i]!.key;
}

// ---------------------------------------------------------------- zoom / pan

export interface View {
  x: number;
  y: number;
  k: number;
}

export const MIN_ZOOM = 0.2;
export const MAX_ZOOM = 3;
export const IDENTITY_VIEW: View = { x: 0, y: 0, k: 1 };

export const screenToWorld = (v: View, p: Point): Point => ({ x: (p.x - v.x) / v.k, y: (p.y - v.y) / v.k });

/** Zoom por `factor` manteniendo fijo el punto de pantalla `at`. */
export function zoomAt(v: View, factor: number, at: Point): View {
  const k = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, v.k * factor));
  const w = screenToWorld(v, at);
  return { k, x: at.x - w.x * k, y: at.y - w.y * k };
}

/** Vista que encuadra `content` centrado en `viewport` con margen (no amplía más de 1). */
export function fitView(content: { width: number; height: number }, viewport: { width: number; height: number }, margin = 24): View {
  if (content.width <= 0 || content.height <= 0 || viewport.width <= 0 || viewport.height <= 0) return IDENTITY_VIEW;
  const k = Math.min(1, Math.max(MIN_ZOOM, Math.min((viewport.width - margin * 2) / content.width, (viewport.height - margin * 2) / content.height)));
  return { k, x: (viewport.width - content.width * k) / 2, y: (viewport.height - content.height * k) / 2 };
}

// ---------------------------------------------------------------- crear relación

/** Siguiente nombre `rel-<n>` libre entre los `RelationDoc` existentes. */
export function nextRelationName(documents: Pick<GraphDocument, "id" | "model_name">[]): string {
  let max = 0;
  for (const d of documents) {
    if (d.model_name !== "RelationDoc") continue;
    const m = /^rel-(\d+)$/.exec(d.id);
    if (m) max = Math.max(max, Number(m[1]));
  }
  return `rel-${max + 1}`;
}

const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

/** Extremo con su etiqueta legible, para armar el título del `RelationDoc`. */
export interface PayloadEnd {
  gid: string;
  label: string;
}

/** Payload del `RelationDoc` para `source → target` (átomos o `GrupoDoc`) con el tipo elegido. */
export function relationPayloadBetween(source: PayloadEnd, target: PayloadEnd, type: RelationTypeSpec): Payload {
  return {
    title: `${clip(source.label, 30)} ${type.name} ${clip(target.label, 30)}`,
    source_id: source.gid,
    target_id: target.gid,
    relation_type: type.name,
    condition: "",
    notes: "",
  };
}

/** Payload del `RelationDoc` para `source → target` con el tipo elegido. */
export function relationPayload(source: Atom, target: Atom, type: RelationTypeSpec): Payload {
  return relationPayloadBetween({ gid: source.gid, label: source.text }, { gid: target.gid, label: target.text }, type);
}

export const truncate = clip;

/** Parte `text` en hasta `maxLines` líneas de `width` caracteres (por palabras); la última se recorta con «…». */
export function wrapLines(text: string, width: number, maxLines: number): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let cur = "";
  let i = 0;
  for (; i < words.length; i++) {
    const w = words[i]!;
    const next = cur ? `${cur} ${w}` : w;
    if (next.length <= width || !cur) cur = next;
    else {
      lines.push(cur);
      cur = w;
      if (lines.length === maxLines - 1) {
        i++;
        break;
      }
    }
  }
  if (cur) {
    const rest = words.slice(i).join(" ");
    lines.push(rest ? `${cur} ${rest}` : cur);
  }
  return lines.slice(0, maxLines).map((l, idx, arr) => (idx === arr.length - 1 || l.length > width ? clip(l, width) : l));
}
