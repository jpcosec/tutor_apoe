/**
 * INFORME · lógica pura de la vista de slots (OPERACIONALIZACION-VISTAS §4).
 *
 * - Consulta de slot: `tipo:decision tag:infra.ingesta estado:confirmado texto libre` ↔ `AtomFilters`.
 * - Vista previa client-side del documento final (viñetas / prosa / tabla) con procedencia.
 * - Gate de publicación y diff de campos a persistir.
 * Nada acá toca DOM ni red.
 */
import { linkKind } from "./atom-graph";
import { ATOM_STATUSES, capitalize, defaultSlotTitle, KIND_LABELS, kindLabel, SLOT_NAMES, type AtomFilters } from "./atoms";
import type { GroupInfo } from "./atom-groups";
import { groupTitle } from "./caso";
import type { Atom, AtomKind, AtomStatus, Edge, GraphDocument, Informe, InformeSlot, InformeSlotEntry, Payload, SlotMode, SlotName } from "./contract";

export const SLOT_LABELS: Record<SlotName, string> = {
  resumen: "Resumen",
  decisiones: "Decisiones",
  riesgos: "Riesgos",
  pendientes: "Pendientes",
};

// ---------------------------------------------------------------- consulta

export type QueryTokenKind = "tipo" | "tag" | "estado" | "base" | "distancia" | "relacion" | "texto";

export interface QueryToken {
  kind: QueryTokenKind;
  /** Texto original del token, tal cual se reescribe. */
  raw: string;
  /** Valor sin prefijo (`decision` en `tipo:decision`). */
  value: string;
  /** `false` si el valor no es válido (`tipo:foo`) o el filtro no aplica (segundo `tag:`). */
  active: boolean;
  /** Etiqueta legible del chip: `Base: Paciente`, `Distancia: 1 salto`, `Tag: Asistente`. */
  label: string;
}

export interface ParsedQuery {
  tokens: QueryToken[];
  filters: AtomFilters;
}

export interface ParseQueryOptions {
  /** Tipos de átomo válidos para `tipo:`; por defecto los de `KIND_LABELS`. */
  kinds?: string[];
  /** `GrupoDoc` para los títulos de `tag:` y `base:` (si no hay, se capitaliza). */
  grupos?: Pick<GroupInfo, "tag" | "title">[];
}

const PREFIXES: Record<string, Exclude<QueryTokenKind, "texto">> = {
  tipo: "tipo",
  tag: "tag",
  estado: "estado",
  base: "base",
  distancia: "distancia",
  relacion: "relacion",
  relación: "relacion",
};

const CHIP_PREFIX: Record<Exclude<QueryTokenKind, "texto">, string> = {
  tipo: "Tipo",
  tag: "Tag",
  estado: "Estado",
  base: "Base",
  distancia: "Distancia",
  relacion: "Relación",
};

/** Etiqueta legible de un chip: `Distancia: 1 salto`, `Base: Paciente`… */
export function chipLabel(kind: QueryTokenKind, value: string, grupos: ParseQueryOptions["grupos"] = []): string {
  if (kind === "texto") return value;
  const prefix = CHIP_PREFIX[kind];
  switch (kind) {
    case "tipo":
      return `${prefix}: ${kindLabel(value)}`;
    case "estado":
      return `${prefix}: ${capitalize(value)}`;
    case "tag":
    case "base":
      return `${prefix}: ${groupTitle(value, grupos)}`;
    case "distancia":
      return /^\d+$/.test(value) ? `${prefix}: ${Number(value)} ${Number(value) === 1 ? "salto" : "saltos"}` : `${prefix}: ${value}`;
    case "relacion":
      return `${prefix}: ${value.split(",").filter(Boolean).map((v) => v.replace(/_/g, " ")).join(", ")}`;
  }
}

/**
 * Consulta de slot: `tipo:regla estado:confirmado tag:asistente base:paciente distancia:1
 * relacion:activa,detalla texto libre` -> tokens (chips) y `AtomFilters`. `tag` y `base`
 * pueden repetirse (unión: ver `matchQuery`); `distancia` exige un entero >= 0 y solo aplica una
 * vez (el segundo es un chip inactivo); `relacion` lleva tipos separados por coma.
 */
export function parseQuery(query: string, opts: ParseQueryOptions = {}): ParsedQuery {
  const validKinds = opts.kinds ?? Object.keys(KIND_LABELS);
  const tokens: QueryToken[] = [];
  const kinds: AtomKind[] = [];
  const statuses: AtomStatus[] = [];
  const relaciones: string[] = [];
  const texts: string[] = [];
  const tagsQ: string[] = [];
  const basesQ: string[] = [];
  let distancia: number | undefined;
  for (const raw of query.split(/\s+/).filter(Boolean)) {
    const m = /^([a-zá-ú]+):(.+)$/i.exec(raw);
    const kind = m ? PREFIXES[m[1]!.toLowerCase()] : undefined;
    if (!m || !kind) {
      tokens.push({ kind: "texto", raw, value: raw, active: true, label: raw });
      texts.push(raw);
      continue;
    }
    const value = m[2]!;
    let active = false;
    if (kind === "tipo" && validKinds.includes(value)) {
      active = true;
      kinds.push(value);
    } else if (kind === "estado" && ATOM_STATUSES.includes(value as AtomStatus)) {
      active = true;
      statuses.push(value as AtomStatus);
    } else if (kind === "tag") {
      active = true;
      tagsQ.push(value);
    } else if (kind === "base") {
      active = true;
      basesQ.push(value);
    } else if (kind === "distancia" && distancia === undefined && /^\d+$/.test(value)) {
      active = true;
      distancia = Number(value);
    } else if (kind === "relacion") {
      active = true;
      relaciones.push(...value.split(",").filter(Boolean));
    }
    tokens.push({ kind, raw, value, active, label: chipLabel(kind, value, opts.grupos) });
  }
  const filters: AtomFilters = {};
  if (kinds.length) filters.kind = kinds.length === 1 ? kinds[0] : kinds;
  if (statuses.length) filters.status = statuses.length === 1 ? statuses[0] : statuses;
  if (tagsQ.length) filters.tag = tagsQ.length === 1 ? tagsQ[0] : tagsQ;
  if (basesQ.length) filters.base = basesQ.length === 1 ? basesQ[0] : basesQ;
  if (distancia !== undefined) filters.distancia = distancia;
  if (relaciones.length) filters.relacion = relaciones;
  if (texts.length) filters.text = texts.join(" ");
  return { tokens, filters };
}

/** Texto de consulta desde los tokens (ida y vuelta con `parseQuery`). */
export function serializeQuery(tokens: Pick<QueryToken, "raw">[]): string {
  return tokens.map((t) => t.raw).join(" ");
}

/** Quita el token `index` (✕ de un chip) y reescribe la consulta. */
export function removeQueryToken(query: string, index: number): string {
  return serializeQuery(parseQuery(query).tokens.filter((_, i) => i !== index));
}

// ---------------------------------------------------------------- persistencia de slots

export type SlotListKey = "atomos" | "pins" | "excluidos";

/** Nombre del campo del `InformeAvanceDoc` que guarda cada parte del slot. */
export function slotField(slot: string, key: SlotListKey | "query" | "modo"): string {
  return key === "atomos" ? slot : `${slot}_${key}`;
}

export interface FieldChange {
  field: string;
  value: string[];
}

/** Campos de lista que cambian entre dos estados del slot: una entrada por campo. */
export function slotChanges(slot: string, before: InformeSlot, after: InformeSlot): FieldChange[] {
  const out: FieldChange[] = [];
  for (const key of ["atomos", "pins", "excluidos"] as SlotListKey[]) {
    const a = before[key];
    const b = after[key];
    if (a.length !== b.length || a.some((x, i) => x !== b[i])) out.push({ field: slotField(slot, key), value: b });
  }
  return out;
}

// ---------------------------------------------------------------- gate

export interface ReviewGate {
  pending: number;
  ready: boolean;
  label: string;
}

/** Gate de publicación: la suma de `nuevos` sin revisar de todos los slots (cualquier nombre). */
export function reviewGate(nuevos: Partial<Record<string, string[]>>): ReviewGate {
  const pending = Object.values(nuevos).reduce((n, list) => n + (list?.length ?? 0), 0);
  return {
    pending,
    ready: pending === 0,
    label: pending === 0 ? "Listo para publicar" : `${pending} ${pending === 1 ? "átomo nuevo" : "átomos nuevos"} por revisar`,
  };
}

// ---------------------------------------------------------------- vista previa

export interface PreviewItem {
  key: string;
  text: string;
  kind: AtomKind;
  /** Átomos de los que viene (procedencia). */
  atoms: Atom[];
  /** Solo en tablas: relación en `edges` o `Sin relación`. */
  relation: string;
  /** Solo en tablas: evidencia estilo maqueta, `<texto del átomo relacionado> (<tipo>)` o `Sin relación`. */
  evidence: string;
}

export interface PreviewSection {
  slot: string;
  /** Título de la sección (`## <label>`). */
  label: string;
  /** Rótulo del slot (`""` si no hay). */
  rotulo: string;
  /** Encabezados de la tabla: tipo del primer átomo (`Criterio`) y `Evidencia`. */
  headers: [string, string];
  modo: SlotMode;
  empty: boolean;
  items: PreviewItem[];
  /** Rutas de la lista que no corresponden a ningún átomo leído. */
  missing: string[];
  /** Prosa unida (solo `modo === "prosa"`). */
  prose: string;
}

export const NO_RELATION = "Sin relación";

function sentence(text: string): string {
  const t = text.trim();
  return /[.!?…]$/.test(t) ? t : `${t}.`;
}

export function relationLabel(atom: Atom, edges: Edge[], byGid: Map<string, Atom>): string {
  const parts: string[] = [];
  for (const e of edges) {
    if (linkKind(e) !== "relation") continue;
    if (e.source === atom.gid) parts.push(`${e.type} → ${byGid.get(e.target)?.text ?? e.target}`);
    else if (e.target === atom.gid) parts.push(`${byGid.get(e.source)?.text ?? e.source} ${e.type} este`);
  }
  return parts.length ? parts.join("; ") : NO_RELATION;
}

/** Evidencia de una fila de tabla: el primer átomo relacionado por una relación, `texto (tipo)`. */
export function evidenceLabel(atom: Atom, edges: Edge[], byGid: Map<string, Atom>): string {
  for (const e of edges) {
    if (linkKind(e) !== "relation") continue;
    const other = e.source === atom.gid ? byGid.get(e.target) : e.target === atom.gid ? byGid.get(e.source) : undefined;
    if (other) return `${other.text} (${e.type.replace(/_/g, " ")})`;
  }
  return NO_RELATION;
}

/** Slots del informe en orden, con título: acepta la lista ordenada o el mapa por nombre. */
function slotEntries(slots: Informe["slots"] | InformeSlotEntry[]): { name: string; titulo: string; rotulo: string; slot: InformeSlot }[] {
  if (Array.isArray(slots)) return slots.map((s) => ({ name: s.name, titulo: s.titulo, rotulo: s.rotulo, slot: s }));
  return Object.entries(slots).flatMap(([name, slot]) => (slot ? [{ name, titulo: defaultSlotTitle(name), rotulo: "", slot }] : []));
}

/**
 * Vista previa del documento final, una sección por slot. Con `informe.slotList` usa el título y
 * rótulo de cada slot; con el mapa `informe.slots` (informe viejo) usa los títulos por defecto.
 */
export function buildPreview(slots: Informe["slots"] | InformeSlotEntry[], atoms: Atom[], edges: Edge[] = []): PreviewSection[] {
  const byPath = new Map(atoms.map((a) => [a.path, a]));
  const byGid = new Map(atoms.map((a) => [a.gid, a]));
  return slotEntries(slots).map(({ name, titulo, rotulo, slot: s }) => {
    const items: PreviewItem[] = [];
    const missing: string[] = [];
    for (const path of s.atomos) {
      const atom = byPath.get(path);
      if (!atom) {
        missing.push(path);
        continue;
      }
      const tabla = s.modo === "tabla";
      items.push({
        key: `${name}:${path}`,
        text: atom.text,
        kind: atom.kind,
        atoms: [atom],
        relation: tabla ? relationLabel(atom, edges, byGid) : "",
        evidence: tabla ? evidenceLabel(atom, edges, byGid) : "",
      });
    }
    return {
      slot: name,
      label: titulo,
      rotulo,
      headers: [items[0] ? kindLabel(items[0].kind) : "Elemento", "Evidencia"] as [string, string],
      modo: s.modo,
      empty: items.length === 0,
      items,
      missing,
      prose: s.modo === "prosa" ? items.map((i) => sentence(i.text)).join(" ") : "",
    };
  });
}

// ---------------------------------------------------------------- publicación

/** Modelo de las fotos inmutables de un informe: un documento por versión. */
export const PUBLICATION_MODEL = "PublicacionDoc";

export interface Publication {
  /** Id del documento (`<informe>-v<N>`). */
  id: string;
  informe: string;
  version: number;
  title: string;
  atoms: string[];
}

/** Publicaciones de un informe, de la más antigua a la más nueva. Ignora documentos sin versión entera. */
export function publicationsOf(documents: GraphDocument[], informeId: string): Publication[] {
  const out: Publication[] = [];
  for (const d of documents) {
    if (d.model_name !== PUBLICATION_MODEL || d.payload.informe !== informeId) continue;
    const version = Number(d.payload.version);
    if (!Number.isInteger(version) || version < 1) continue;
    const atoms = Array.isArray(d.payload.atoms) ? d.payload.atoms.filter((a): a is string => typeof a === "string") : [];
    out.push({ id: d.id, informe: informeId, version, title: typeof d.payload.title === "string" ? d.payload.title : "", atoms });
  }
  return out.sort((a, b) => a.version - b.version);
}

/** Mayor versión publicada; `0` si no hay ninguna. */
export function latestVersion(publications: Pick<Publication, "version">[]): number {
  return publications.reduce((m, p) => Math.max(m, p.version), 0);
}

export const nextVersion = (publications: Pick<Publication, "version">[]): number => latestVersion(publications) + 1;

/** Nombre del documento de una publicación: `<informe>-v<N>`. */
export const publicationName = (informeId: string, version: number): string => `${informeId}-v${version}`;

/** Rutas de los átomos de la foto: unión de los slots, sin repetir y en orden de slot. */
export function snapshotAtoms(slots: Partial<Record<string, Pick<InformeSlot, "atomos">>> | Pick<InformeSlot, "atomos">[]): string[] {
  const seen = new Set<string>();
  for (const s of Object.values(slots)) for (const p of s?.atomos ?? []) seen.add(p);
  return [...seen];
}

const OLD_SLOTS: Pick<InformeSlotEntry, "name" | "titulo">[] = SLOT_NAMES.map((name) => ({ name, titulo: SLOT_LABELS[name] }));

/**
 * Parte el markdown que renderiza SLDB (`GET /render`) en el título y una sección por slot.
 * Quita el frontmatter de configuración. `slots` da los `## <titulo>` conocidos (por defecto los
 * 4 del informe viejo); las secciones salen con el NOMBRE del slot como clave. Un `## X` que no
 * sea un slot conocido es un error: no se descarta contenido en silencio.
 */
export function splitRendered(markdown: string, slots: Pick<InformeSlotEntry, "name" | "titulo">[] = OLD_SLOTS): { title: string; sections: Record<string, string> } {
  const text = markdown.replace(/\r\n/g, "\n").replace(/^---\n[\s\S]*?\n---\n+/, "");
  const byTitle = new Map<string, string>();
  for (const s of slots) if (!byTitle.has(s.titulo)) byTitle.set(s.titulo, s.name);
  const sections: Record<string, string> = Object.fromEntries(slots.map((s) => [s.name, ""]));
  let title = "";
  let current: string | null = null;
  const buf: string[] = [];
  const flush = () => {
    if (current) sections[current] = buf.join("\n").trim();
    buf.length = 0;
  };
  for (const line of text.split("\n")) {
    const h2 = /^## (.+?)\s*$/.exec(line);
    if (h2) {
      flush();
      const slot = byTitle.get(h2[1]!);
      if (!slot) throw new Error(`El informe renderizado trae la sección «${h2[1]}», que la publicación no conoce.`);
      current = slot;
      continue;
    }
    const h1 = /^# (.+?)\s*$/.exec(line);
    if (h1 && current === null && !title) {
      title = h1[1]!;
      continue;
    }
    if (current) buf.push(line);
  }
  flush();
  return { title, sections };
}

/**
 * Payload de `PublicacionDoc` a partir del render real de SLDB. El modelo lleva una sección por slot
 * (campo con el NOMBRE del slot; SLDB rechaza headings dentro de un campo), así que el "cuerpo" es
 * la suma de esas secciones. Parte por los `## <titulo>` de los slots del informe dado.
 */
export function publicationPayload(input: { informe: Informe; version: number; markdown: string }): Payload {
  const { title, sections } = splitRendered(input.markdown, input.informe.slotList);
  const fallback = typeof input.informe.payload.title === "string" ? input.informe.payload.title : "";
  return {
    informe: input.informe.id,
    version: input.version,
    atoms: snapshotAtoms(input.informe.slotList),
    title: title || fallback || input.informe.id,
    ...sections,
  };
}

export interface PublishState {
  /** `Publicar v3`. */
  label: string;
  enabled: boolean;
  /** Por qué está deshabilitado (para el `title` del botón); vacío si está habilitado. */
  reason: string;
  /** `Publicado como v2` o `Sin publicar`. */
  published: string;
}

/** Estado del botón: habilitado si el gate está limpio, hay algo que publicar y no se está publicando. */
export function publishState(input: { gate: ReviewGate; publications: Pick<Publication, "version">[]; atomCount: number; publishing: boolean }): PublishState {
  const latest = latestVersion(input.publications);
  const label = `Publicar v${latest + 1}`;
  const published = latest > 0 ? `Publicado como v${latest}` : "Sin publicar";
  const reason = input.publishing
    ? "Publicando…"
    : !input.gate.ready
      ? "Revisa los átomos nuevos antes de republicar"
      : input.atomCount === 0
        ? "No hay átomos que publicar"
        : "";
  return { label, enabled: reason === "", reason, published };
}
