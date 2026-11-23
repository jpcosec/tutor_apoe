/**
 * ÁTOMOS · lógica pura de las vistas de átomos (OPERACIONALIZACION-VISTAS.md).
 *
 * Un átomo es un documento `AtomDoc` anclado a un tramo del campo `body` de una fuente
 * (`FuenteDoc` del caso nuevo o `ActaDoc` del viejo).
 * Nada acá toca DOM ni red: recibe documentos/aristas ya leídos y devuelve valores nuevos.
 *
 * Identidad: `Atom.id` es el id de documento (`a3`, el de `/document` y `/save`);
 * `Atom.gid` es `AtomDoc:a3`, el que usan las aristas. Las listas de un informe (slots,
 * pins, excluidos) guardan RUTAS de átomo (`Atom.path`, p. ej. `docs/atoms/a3.md`).
 */
import type {
  Acta,
  AnchorState,
  Atom,
  AtomKind,
  AtomStatus,
  Edge,
  GraphDocument,
  Informe,
  InformeSlot,
  InformeSlotEntry,
  InformeSlotMap,
  Payload,
  RelationTypeSpec,
  SlotMode,
  SlotName,
} from "./contract";
import { GROUP_MODEL, groupGid, isGroupGid, tagOfGroupGid } from "./atom-groups";

export const ATOM_MODEL = "AtomDoc";
/** Los 5 tipos del caso viejo (`ActaDoc`). Los tipos ya no son fijos: ver `KIND_LABELS`. */
export const ATOM_KINDS: AtomKind[] = ["entidad", "hecho", "decision", "pendiente", "riesgo"];
/**
 * Registro de tipos conocidos (clave -> etiqueta): los 5 del caso viejo y los 5 de Levira.
 * Un tipo que no esté acá es válido igual: `kindLabel` cae a la clave capitalizada. El color
 * por tipo lo decide la vista (CSS); el núcleo solo expone la clave.
 */
export const KIND_LABELS: Record<string, string> = {
  entidad: "Entidad",
  hecho: "Hecho",
  decision: "Decisión",
  pendiente: "Pendiente",
  riesgo: "Riesgo",
  regla: "Regla",
  criterio: "Criterio",
  logistica: "Logística",
  paciente: "Dato del paciente",
  pregunta: "Pregunta",
};

/** Primera letra en mayúscula; `_` y `-` pasan a espacio (`consulta_por` -> `Consulta por`). */
export function capitalize(text: string): string {
  const t = text.trim().replace(/[_-]+/g, " ");
  return t ? t[0]!.toUpperCase() + t.slice(1) : "";
}

/** Etiqueta legible de un tipo de átomo; los desconocidos, la clave capitalizada. */
export function kindLabel(kind: string): string {
  return Object.prototype.hasOwnProperty.call(KIND_LABELS, kind) ? KIND_LABELS[kind]! : capitalize(kind);
}
export const ATOM_STATUSES: AtomStatus[] = ["propuesto", "confirmado", "descartado"];
export const SLOT_NAMES: SlotName[] = ["resumen", "decisiones", "riesgos", "pendientes"];
export const SLOT_MODES: SlotMode[] = ["viñetas", "prosa", "tabla"];
/** Largo máximo del `text` de un átomo creado desde una selección. */
export const ATOM_TEXT_MAX = 80;

const str = (v: unknown, fallback = ""): string => (typeof v === "string" ? v : fallback);
const num = (v: unknown, fallback = 0): number => (typeof v === "number" && Number.isFinite(v) ? v : fallback);
const strings = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

// ---------------------------------------------------------------- lectura de documentos

/**
 * Convierte los `AtomDoc` de `/graph`. `kind` se conserva tal cual (cualquier string; vacío o
 * ausente cae a `hecho`); un `status` fuera de enum cae a `propuesto`.
 */
export function atomsFromDocuments(docs: GraphDocument[]): Atom[] {
  return docs
    .filter((d) => d.model_name === ATOM_MODEL)
    .map((d) => {
      const p = d.payload;
      const kind = str(p.kind).trim() || "hecho";
      const status = ATOM_STATUSES.includes(p.status as AtomStatus) ? (p.status as AtomStatus) : "propuesto";
      return {
        id: d.id,
        gid: `${ATOM_MODEL}:${d.id}`,
        path: d.path,
        version: d.version,
        kind,
        status,
        source: str(p.source),
        source_field: str(p.source_field, "body"),
        start: num(p.start),
        end: num(p.end),
        tags: strings(p.tags),
        text: str(p.text),
        quote: str(p.quote),
        conf: num(p.conf, 1),
      };
    });
}

export function relationTypesFromDocuments(docs: GraphDocument[]): RelationTypeSpec[] {
  return docs
    .filter((d) => d.model_name === "RelationTypeDoc")
    .map((d) => ({
      id: d.id,
      name: str(d.payload.name, d.id),
      source_types: strings(d.payload.source_types),
      target_types: strings(d.payload.target_types),
      cardinality: str(d.payload.cardinality),
      description: str(d.payload.description),
    }));
}

export function actasFromDocuments(docs: GraphDocument[]): Acta[] {
  return docs
    .filter((d) => d.model_name === "ActaDoc")
    .map((d) => ({
      id: d.id,
      gid: `ActaDoc:${d.id}`,
      path: d.path,
      version: d.version,
      title: str(d.payload.title, d.id),
      body: str(d.payload.body),
    }));
}

export function slotFromPayload(payload: Payload, slot: string): InformeSlot {
  const modo = payload[`${slot}_modo`];
  return {
    atomos: strings(payload[slot]),
    query: str(payload[`${slot}_query`]),
    pins: strings(payload[`${slot}_pins`]),
    excluidos: strings(payload[`${slot}_excluidos`]),
    modo: SLOT_MODES.includes(modo as SlotMode) ? (modo as SlotMode) : "viñetas",
  };
}

/** Títulos por defecto de los 4 slots del informe viejo. */
const DEFAULT_SLOT_TITLES: Record<string, string> = { resumen: "Resumen", decisiones: "Decisiones", riesgos: "Riesgos", pendientes: "Pendientes" };

/** Título por defecto de un slot sin `<slot>_titulo`: el del informe viejo o el nombre capitalizado. */
export const defaultSlotTitle = (name: string): string => DEFAULT_SLOT_TITLES[name] ?? capitalize(name);

/** Modelo del informe viejo, de slots fijos. */
export const INFORME_MODEL = "InformeAvanceDoc";

/**
 * Nombres de slot de un payload: las claves `<x>_query`, en el orden de sus claves. El informe
 * viejo (`InformeAvanceDoc`) siempre tiene los 4 fijos, aunque falten sus `_query`.
 */
export function slotNamesOf(model: string, payload: Payload): string[] {
  if (model === INFORME_MODEL) return [...SLOT_NAMES];
  const names: string[] = [];
  for (const key of Object.keys(payload)) {
    const m = /^(.+)_query$/.exec(key);
    if (m && typeof payload[key] === "string" && !names.includes(m[1]!)) names.push(m[1]!);
  }
  return names;
}

/** Lee informes de CUALQUIER modelo con slots (`InformeAvanceDoc`, `SalidaDoc`, futuros). */
export function informesFromDocuments(docs: GraphDocument[]): Informe[] {
  const out: Informe[] = [];
  for (const d of docs) {
    const names = slotNamesOf(d.model_name, d.payload);
    if (d.model_name !== INFORME_MODEL && names.length === 0) continue;
    const slotList: InformeSlotEntry[] = names.map((name) => ({
      ...slotFromPayload(d.payload, name),
      name,
      titulo: str(d.payload[`${name}_titulo`]) || defaultSlotTitle(name),
      rotulo: str(d.payload[`${name}_rotulo`]),
    }));
    // La vista por nombre lleva SOLO los campos de `InformeSlot` (sin name/titulo/rotulo).
    const slots = Object.fromEntries(names.map((name) => [name, slotFromPayload(d.payload, name)])) as InformeSlotMap;
    out.push({ id: d.id, path: d.path, version: d.version, modelName: d.model_name, payload: d.payload, slots, slotList });
  }
  return out;
}

// ---------------------------------------------------------------- ancla

export interface AnchorCheck {
  state: AnchorState;
  /** Solo en `drifted`: índice donde la cita está ahora (la ocurrencia más cercana a `start`). */
  movedTo?: number;
}

/** El ancla se calcula contra el texto actual del campo; nunca se guarda. */
export function anchorState(body: string, atom: Pick<Atom, "start" | "end" | "quote">): AnchorCheck {
  const { quote } = atom;
  if (!quote) return { state: "orphan" };
  if (body.slice(atom.start, atom.end) === quote) return { state: "intact" };
  let best = -1;
  let from = body.indexOf(quote);
  while (from !== -1) {
    if (best === -1 || Math.abs(from - atom.start) < Math.abs(best - atom.start)) best = from;
    from = body.indexOf(quote, from + 1);
  }
  return best === -1 ? { state: "orphan" } : { state: "drifted", movedTo: best };
}

/** Offsets nuevos para un ancla `drifted`; `null` si no hay nada que reparar (intacta u huérfana). */
export function repairAnchor(body: string, atom: Pick<Atom, "start" | "end" | "quote">): { start: number; end: number } | null {
  const check = anchorState(body, atom);
  if (check.state !== "drifted" || check.movedTo === undefined) return null;
  return { start: check.movedTo, end: check.movedTo + atom.quote.length };
}

// ---------------------------------------------------------------- grupos

export interface GroupNode {
  /** Ruta completa del grupo: `infra.ingesta`. */
  id: string;
  /** Último segmento: `ingesta`. */
  name: string;
  /** Átomos distintos en este grupo o en cualquier subgrupo. */
  count: number;
  /** Ids de los átomos cuyo tag es exactamente este grupo. */
  atomIds: string[];
  children: GroupNode[];
}

/** Árbol de grupos por tags con puntos. Un átomo con varios tags cuenta en cada rama. */
export function groupTree(atoms: Atom[]): GroupNode[] {
  interface Build extends GroupNode {
    all: Set<string>;
    kids: Map<string, Build>;
  }
  const roots = new Map<string, Build>();
  for (const atom of atoms) {
    for (const tag of atom.tags) {
      const parts = tag.split(".").filter(Boolean);
      let level = roots;
      let id = "";
      parts.forEach((part, i) => {
        id = id ? `${id}.${part}` : part;
        let node = level.get(part);
        if (!node) {
          node = { id, name: part, count: 0, atomIds: [], children: [], all: new Set(), kids: new Map() };
          level.set(part, node);
        }
        node.all.add(atom.id);
        if (i === parts.length - 1 && !node.atomIds.includes(atom.id)) node.atomIds.push(atom.id);
        level = node.kids;
      });
    }
  }
  const finish = (level: Map<string, Build>): GroupNode[] =>
    [...level.values()]
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((n) => ({ id: n.id, name: n.name, count: n.all.size, atomIds: n.atomIds, children: finish(n.kids) }));
  return finish(roots);
}

/** ¿El átomo pertenece al grupo `group` (él mismo o un subgrupo)? */
export function inGroup(atom: Pick<Atom, "tags">, group: string): boolean {
  return atom.tags.some((t) => t === group || t.startsWith(`${group}.`));
}

// ---------------------------------------------------------------- relaciones

const admits = (types: string[], model: string) => types.length === 0 || types.includes(model);

/**
 * Tipos de relación propios de los átomos: los que nombran `AtomDoc` de forma explícita en
 * ambos extremos. Los 13 tipos estructurales del índice (`has_model`, `references`…) también
 * son `RelationTypeDoc`, pero traen extremos vacíos u otras clases y no se ofrecen ni filtran.
 */
export function atomRelationTypes(types: RelationTypeSpec[]): RelationTypeSpec[] {
  return types.filter((t) => t.source_types.includes(ATOM_MODEL) && t.target_types.includes(ATOM_MODEL));
}

/**
 * Tipos de relación ofrecibles al arrastrar `sourceAtom` → `targetAtom`: los tipos de átomo
 * (`atomRelationTypes`) que admiten `AtomDoc` en ambos extremos y para los que no existe ya la
 * misma arista en `edges`. Un átomo no se relaciona consigo mismo.
 */
export function validRelationTypes(types: RelationTypeSpec[], sourceAtom: Atom, targetAtom: Atom, edges: Edge[] = []): RelationTypeSpec[] {
  if (sourceAtom.gid === targetAtom.gid) return [];
  return atomRelationTypes(types).filter(
    (t) =>
      admits(t.source_types, ATOM_MODEL) &&
      admits(t.target_types, ATOM_MODEL) &&
      !edges.some((e) => e.type === t.name && e.source === sourceAtom.gid && e.target === targetAtom.gid),
  );
}

export interface InheritedEdge {
  /** Arista original, la del grupo. */
  edge: Edge;
  /** Átomo miembro que la hereda. */
  atomId: string;
  atomGid: string;
  /** Grupo del que viene. */
  via: string;
  /** Extremos con el grupo sustituido por el átomo: `Model:name`. */
  source: string;
  target: string;
  /** Siempre `true`: se calcula, no se guarda. */
  inherited: true;
}

/**
 * Cómo puede nombrar una arista al grupo `tag` en sus extremos: `GrupoDoc:<slug>` (el formato
 * actual, ver `atom-groups`) y, por compatibilidad, los formatos viejos (`tag`, `tag:x`,
 * `Group:x`, `semantic_tag/x`).
 */
export function groupEndpoints(tag: string): string[] {
  return [groupGid(tag), tag, `tag:${tag}`, `Group:${tag}`, `semantic_tag/${tag}`, `sldb://semantic_tag/${tag}`];
}

/** Extremo de una relación a crear: un átomo o un grupo (`GrupoDoc`). */
export interface RelEnd {
  gid: string;
  model: string;
}

/**
 * Como `validRelationTypes` pero con extremos átomo O grupo: el tipo debe admitir el modelo de
 * cada extremo (`AtomDoc` / `GrupoDoc`) y la arista exacta no debe existir. Entre dos grupos no
 * se ofrece nada (no hay producto cartesiano de grupos).
 */
export function validRelationTypesBetween(types: RelationTypeSpec[], source: RelEnd, target: RelEnd, edges: Edge[] = []): RelationTypeSpec[] {
  if (source.gid === target.gid) return [];
  if (source.model === GROUP_MODEL && target.model === GROUP_MODEL) return [];
  return atomRelationTypes(types).filter(
    (t) =>
      admits(t.source_types, source.model) &&
      admits(t.target_types, target.model) &&
      !edges.some((e) => e.type === t.name && e.source === source.gid && e.target === target.gid),
  );
}

/**
 * Aristas heredadas: las que tocan al grupo `groupId` (tag con puntos) se proyectan sobre cada
 * átomo miembro (incluidos subgrupos). Si ambos extremos son grupos/miembros, se omite la
 * arista para no inventar producto cartesiano: solo se hereda cuando el otro extremo es fijo.
 */
export function inheritedEdges(edges: Edge[], groupId: string, atoms: Atom[]): InheritedEdge[] {
  const ends = groupEndpoints(groupId);
  const members = atoms.filter((a) => inGroup(a, groupId));
  const out: InheritedEdge[] = [];
  for (const edge of edges) {
    const srcIs = ends.includes(edge.source);
    const tgtIs = ends.includes(edge.target);
    if (srcIs === tgtIs) continue;
    for (const atom of members) {
      out.push({
        edge,
        atomId: atom.id,
        atomGid: atom.gid,
        via: groupId,
        source: srcIs ? atom.gid : edge.source,
        target: tgtIs ? atom.gid : edge.target,
        inherited: true,
      });
    }
  }
  return out;
}

// ---------------------------------------------------------------- slots de informe (§4)

/** Resultado de Actualizar: nada entra a la lista sin aceptarlo. */
export interface SlotRefresh {
  /** Rutas que salen de la consulta y no están en lista, pins ni excluidos. */
  nuevos: string[];
  /** Rutas de la lista que la consulta ya no devuelve y no están fijadas (la UI puede avisarlo). */
  salieron: string[];
}

export function refreshSlot(slot: Pick<InformeSlot, "atomos" | "pins" | "excluidos">, queryResults: string[]): SlotRefresh {
  const known = new Set([...slot.atomos, ...slot.pins, ...slot.excluidos]);
  const nuevos = [...new Set(queryResults)].filter((p) => !known.has(p));
  const results = new Set(queryResults);
  const pinned = new Set(slot.pins);
  return { nuevos, salieron: slot.atomos.filter((p) => !results.has(p) && !pinned.has(p)) };
}

const uniq = (xs: string[]) => [...new Set(xs)];
const without = (xs: string[], x: string) => xs.filter((y) => y !== x);

/** Acepta un `nuevo`: entra a la lista (y sale de excluidos si estaba). */
export function acceptAtom(slot: InformeSlot, path: string): InformeSlot {
  return { ...slot, atomos: uniq([...slot.atomos, path]), excluidos: without(slot.excluidos, path) };
}

/** Excluye: sale de la lista y de pins; no volverá como `nuevo` en próximas actualizaciones. */
export function excludeAtom(slot: InformeSlot, path: string): InformeSlot {
  return { ...slot, atomos: without(slot.atomos, path), pins: without(slot.pins, path), excluidos: uniq([...slot.excluidos, path]) };
}

/** Fija: entra a pins y a la lista, y sobrevive a la consulta. */
export function pinAtom(slot: InformeSlot, path: string): InformeSlot {
  return { ...slot, pins: uniq([...slot.pins, path]), atomos: uniq([...slot.atomos, path]), excluidos: without(slot.excluidos, path) };
}

/** Suelta el pin; el átomo se queda en la lista. */
export function unpinAtom(slot: InformeSlot, path: string): InformeSlot {
  return { ...slot, pins: without(slot.pins, path) };
}

/** Deshace una exclusión: el átomo vuelve a poder aparecer como `nuevo`. */
export function unexcludeAtom(slot: InformeSlot, path: string): InformeSlot {
  return { ...slot, excluidos: without(slot.excluidos, path) };
}

// ---------------------------------------------------------------- consulta local

export interface AtomFilters {
  kind?: AtomKind | AtomKind[];
  status?: AtomStatus | AtomStatus[];
  /**
   * Grupo: prefijo (`infra` incluye `infra.ingesta`) o, si no es prefijo, segmentos contiguos
   * del tag (`asistente` calza `programa.asistente`). Sin distinguir mayúsculas.
   */
  tag?: string | string[];
  /** Base = 1er segmento del tag (`paciente` en `paciente.situacion`). Sin distinguir mayúsculas. */
  base?: string | string[];
  /**
   * Saltos por relaciones (entero >= 0). Ver `matchQuery`: amplía el resultado con los átomos a
   * hasta N saltos de los que calzan el resto de los filtros. Necesita las aristas.
   */
  distancia?: number;
  /** Tipos de relación: el átomo debe tener al menos una relación de alguno de estos tipos. */
  relacion?: string[];
  /** Subcadena, sin distinguir mayúsculas, sobre `text`, `quote` y tags. */
  text?: string;
}

/** ¿El átomo está en el grupo `tag` (prefijo) o lo nombra por segmentos contiguos (`asistente`)? */
export function atomHasTag(atom: Pick<Atom, "tags">, tag: string): boolean {
  const want = tag.toLowerCase().split(".").filter(Boolean);
  if (want.length === 0) return false;
  return atom.tags.some((t) => {
    const parts = t.toLowerCase().split(".").filter(Boolean);
    for (let i = 0; i + want.length <= parts.length; i++) if (want.every((w, k) => parts[i + k] === w)) return true;
    return false;
  });
}

/** Base de un tag (1er segmento). Ver también `baseOf` en core/caso. */
const firstSegment = (tag: string): string => tag.split(".").filter(Boolean)[0] ?? "";

const isRelationEdge = (e: Edge): boolean => e.origin.startsWith("relation") || e.relationDoc !== null;

/**
 * Vecindad por relaciones entre átomos: `gid -> gids` adyacentes, SIN dirección. Solo aristas de
 * relación (`RelationDoc`); las que nombran un grupo (`GrupoDoc:<slug>`) se proyectan a cada
 * átomo miembro (como `inheritedEdges`). Aristas entre dos grupos o con extremos desconocidos
 * se ignoran.
 */
export function relationAdjacency(atoms: Atom[], edges: Edge[]): Map<string, Set<string>> {
  const byGid = new Set(atoms.map((a) => a.gid));
  const tags = [...new Set(atoms.flatMap((a) => a.tags))];
  const membersOf = (end: string): string[] => {
    if (byGid.has(end)) return [end];
    const tag = tagOfGroupGid(end, tags);
    return tag ? atoms.filter((a) => inGroup(a, tag)).map((a) => a.gid) : [];
  };
  const adj = new Map<string, Set<string>>();
  const link = (a: string, b: string) => {
    if (a === b) return;
    if (!adj.has(a)) adj.set(a, new Set());
    adj.get(a)!.add(b);
  };
  for (const e of edges) {
    if (!isRelationEdge(e)) continue;
    const srcIsAtom = byGid.has(e.source);
    const tgtIsAtom = byGid.has(e.target);
    if (!srcIsAtom && !tgtIsAtom) continue;
    if (!srcIsAtom && !isGroupGid(e.source)) continue;
    if (!tgtIsAtom && !isGroupGid(e.target)) continue;
    for (const s of membersOf(e.source)) for (const t of membersOf(e.target)) {
      link(s, t);
      link(t, s);
    }
  }
  return adj;
}

/**
 * Resolvedor de consulta de v1, EN CLIENTE: la consulta por servidor (composición por query,
 * OPERACIONALIZACION §4 [falta]) no existe aún. Cuando exista, `refreshSlot` recibe sus
 * resultados en lugar de estos.
 *
 * `base` y `tag` (uno o varios valores) son PERTENENCIA A GRUPO y se combinan con O entre sí: el
 * átomo pasa si está en alguna de las bases o de los tags dados (`base:paciente tag:asistente` =
 * la base paciente MÁS el subgrupo asistente). Sobre ese resultado, `kind`, `status` y
 * `relacion` se combinan con Y (los que faltan no filtran). `relacion`: el átomo tiene al menos una relación (origen o destino) de alguno de esos
 * tipos. `text` (subcadena en text/quote/tags) solo filtra en ausencia de los demás filtros. `distancia: N` (con `edges`) es una AMPLIACIÓN: el resultado son los
 * átomos que calzan todo lo demás (las semillas) MÁS los que están a N saltos o menos de
 * alguna semilla por relaciones (no dirigidas, incluidas las heredadas de grupos; ver
 * `relationAdjacency`). Los vecinos agregados NO tienen que calzar los otros filtros.
 * `distancia` sola no genera nada (sin semillas; con solo texto, las semillas son las del texto).
 * `distancia: 0` equivale a no ampliar. Sin `edges` no se amplía. El orden es el de `atoms`.
 * (La maqueta solo MUESTRA el chip `Distancia: 1 salto`; no calcula nada: esta es la definición.)
 */
export function matchQuery(atoms: Atom[], filters: AtomFilters, edges: Edge[] = []): Atom[] {
  const list = <T,>(v: T | T[] | undefined): T[] | null => (v === undefined ? null : Array.isArray(v) ? v : [v]);
  const kinds = list(filters.kind);
  const statuses = list(filters.status);
  const needle = filters.text?.trim().toLowerCase();
  const asList = (v: string | string[] | undefined): string[] => (v === undefined ? [] : Array.isArray(v) ? v : [v]).map((x) => x.trim()).filter(Boolean);
  const bases = asList(filters.base).map((b) => b.toLowerCase());
  const tagList = asList(filters.tag);
  const relTypes = filters.relacion?.length ? new Set(filters.relacion) : null;
  const relatedGids = relTypes
    ? new Set(edges.filter((e) => isRelationEdge(e) && relTypes.has(e.type)).flatMap((e) => [e.source, e.target]))
    : null;
  const structural = !!(kinds || statuses || tagList.length || bases.length || relTypes);
  // El texto libre solo filtra cuando NO hay otros filtros: en una consulta con tokens es la
  // descripción en prosa del slot (`tag:asistente reglas del asistente...`) y no debe vaciarla.
  const textNeedle = structural ? undefined : needle;
  // `distancia` sola (sin otros filtros ni texto) no tiene semillas: no genera nada.
  if (!structural && filters.distancia !== undefined && !needle) return [];
  const seeds = atoms.filter((a) => {
    if (kinds && !kinds.includes(a.kind)) return false;
    if (statuses && !statuses.includes(a.status)) return false;
    if (bases.length || tagList.length) {
      const inGroups =
        bases.some((b) => a.tags.some((t) => firstSegment(t).toLowerCase() === b)) || tagList.some((t) => atomHasTag(a, t));
      if (!inGroups) return false;
    }
    if (relatedGids && !relatedGids.has(a.gid)) return false;
    if (textNeedle && !`${a.text} ${a.quote} ${a.tags.join(" ")}`.toLowerCase().includes(textNeedle)) return false;
    return true;
  });
  const hops = filters.distancia;
  if (hops === undefined || !Number.isInteger(hops) || hops <= 0 || edges.length === 0) return seeds;
  const adj = relationAdjacency(atoms, edges);
  const reached = new Set(seeds.map((a) => a.gid));
  let frontier = [...reached];
  for (let d = 0; d < hops && frontier.length; d++) {
    const next: string[] = [];
    for (const g of frontier) for (const n of adj.get(g) ?? []) if (!reached.has(n)) (reached.add(n), next.push(n));
    frontier = next;
  }
  return atoms.filter((a) => reached.has(a.gid));
}

// ---------------------------------------------------------------- creación

/** Payload de un átomo nuevo desde una selección `[from, to)` del campo `body` del acta. */
export function selectionToAtomPayload(body: string, from: number, to: number, kind: AtomKind, source: string): Payload {
  const start = Math.max(0, Math.min(from, to));
  const end = Math.min(body.length, Math.max(from, to));
  const quote = body.slice(start, end);
  return {
    kind,
    status: "propuesto",
    source,
    source_field: "body",
    start,
    end,
    tags: [],
    text: quote.slice(0, ATOM_TEXT_MAX),
    quote,
    conf: 1,
  };
}

/** Siguiente nombre `aN` libre. */
export function nextAtomName(existingNames: string[]): string {
  let max = 0;
  for (const name of existingNames) {
    const m = /^a(\d+)$/.exec(name);
    if (m) max = Math.max(max, Number(m[1]));
  }
  return `a${max + 1}`;
}
