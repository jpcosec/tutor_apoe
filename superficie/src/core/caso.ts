/**
 * CASO · lógica pura del caso "de fuentes a respuesta" (Levira): fuentes de texto, bases de
 * conocimiento con subgrupos, y la respuesta con su procedencia por frase.
 *
 * Sirve a los dos modelos de datos: el viejo (`ActaDoc`, 5 tipos) y el nuevo (`FuenteDoc`,
 * `GrupoDoc`, `RespuestaDoc`). Nada acá toca DOM ni red.
 */
import { capitalize, groupTree } from "./atoms";
import type { GroupInfo } from "./atom-groups";
import type { Atom, Fuente, GraphDocument, Respuesta, RespuestaFrase } from "./contract";

export const FUENTE_MODEL = "FuenteDoc";
export const ACTA_MODEL = "ActaDoc";
export const RESPUESTA_MODEL = "RespuestaDoc";

const str = (v: unknown, fallback = ""): string => (typeof v === "string" ? v : fallback);
const strings = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

// ---------------------------------------------------------------- fuentes

/** `FuenteDoc` de `/graph`. */
export function fuentesFromDocuments(docs: GraphDocument[]): Fuente[] {
  return docs
    .filter((d) => d.model_name === FUENTE_MODEL)
    .map((d) => ({
      id: d.id,
      gid: `${FUENTE_MODEL}:${d.id}`,
      path: d.path,
      version: d.version,
      title: str(d.payload.title, d.id),
      tipo: str(d.payload.tipo),
      base: str(d.payload.base),
      descripcion: str(d.payload.descripcion),
      body: str(d.payload.body),
    }));
}

/**
 * Fuentes de AMBOS modelos con la misma forma, en el orden de los documentos: `FuenteDoc` tal
 * cual y `ActaDoc` como fuente de tipo `acta`, base y descripción vacías.
 */
export function sourcesFromDocuments(docs: GraphDocument[]): Fuente[] {
  const out: Fuente[] = [];
  for (const d of docs) {
    if (d.model_name === FUENTE_MODEL) out.push(...fuentesFromDocuments([d]));
    else if (d.model_name === ACTA_MODEL)
      out.push({ id: d.id, gid: `${ACTA_MODEL}:${d.id}`, path: d.path, version: d.version, title: str(d.payload.title, d.id), tipo: "acta", base: "", descripcion: "", body: str(d.payload.body) });
  }
  return out;
}

/** Fuente de un átomo (por `atom.source`), o `undefined`. */
export function fuenteOf(atom: Pick<Atom, "source">, fuentes: Fuente[]): Fuente | undefined {
  return fuentes.find((f) => f.gid === atom.source);
}

// ---------------------------------------------------------------- bases y subgrupos

const segments = (tag: string): string[] => tag.split(".").filter(Boolean);

/** Base de un tag: su 1er segmento (`programa` en `programa.asistente`); `""` si no hay. */
export const baseOf = (tag: string): string => segments(tag)[0] ?? "";

/** Subgrupo de un tag: su 2º segmento (`asistente`); `""` si el tag es solo la base. */
export const subgroupOf = (tag: string): string => segments(tag)[1] ?? "";

/**
 * Título de display de un grupo. `tag` puede ser completo (`programa.asistente`) o un segmento
 * suelto (`asistente`, como en `tag:asistente`). Usa el `title` del `GrupoDoc` (coincidencia
 * exacta de tag, luego por sufijo de segmentos, sin distinguir mayúsculas); si no hay GrupoDoc,
 * o su título está vacío o es el propio tag, capitaliza el último segmento.
 */
export function groupTitle(tag: string, grupos: Pick<GroupInfo, "tag" | "title">[] = []): string {
  const want = tag.toLowerCase();
  const found =
    grupos.find((g) => g.tag.toLowerCase() === want) ?? grupos.find((g) => g.tag.toLowerCase().endsWith(`.${want}`));
  const title = found?.title.trim();
  if (title && title !== found?.tag) return title;
  const last = segments(tag).at(-1) ?? tag;
  return capitalize(last);
}

export interface SubgroupNode {
  /** `programa.asistente`. */
  tag: string;
  title: string;
  count: number;
  atomIds: string[];
}

export interface BaseNode {
  /** 1er segmento tal cual está en los datos: `programa`. */
  base: string;
  title: string;
  /** Átomos distintos de la base. */
  count: number;
  subgroups: SubgroupNode[];
}

/**
 * Bases y subgrupos, ordenados por PRIMERA APARICIÓN en `atoms` (y sus tags). Un átomo con
 * varios tags cuenta en cada rama, una vez por nodo. Los tags de 3+ segmentos suben al
 * subgrupo de sus dos primeros. Reutiliza `groupTree` para los conteos.
 */
export function basesTree(atoms: Atom[], grupos: Pick<GroupInfo, "tag" | "title">[] = []): BaseNode[] {
  const order: string[] = [];
  const subOrder = new Map<string, string[]>();
  for (const atom of atoms) {
    for (const tag of atom.tags) {
      const [b, sub] = segments(tag);
      if (!b) continue;
      if (!order.includes(b)) order.push(b);
      if (sub) {
        const list = subOrder.get(b) ?? [];
        if (!list.includes(sub)) list.push(sub);
        subOrder.set(b, list);
      }
    }
  }
  const tree = groupTree(atoms);
  return order.map((b) => {
    const root = tree.find((n) => n.id === b);
    return {
      base: b,
      title: groupTitle(b, grupos),
      count: root?.count ?? 0,
      subgroups: (subOrder.get(b) ?? []).map((sub) => {
        const tag = `${b}.${sub}`;
        const node = root?.children.find((c) => c.id === tag);
        const atomIds = atoms.filter((a) => a.tags.some((t) => t === tag || t.startsWith(`${tag}.`))).map((a) => a.id);
        return { tag, title: groupTitle(tag, grupos), count: node?.count ?? atomIds.length, atomIds };
      }),
    };
  });
}

// ---------------------------------------------------------------- respuesta

function frasesOf(v: unknown): RespuestaFrase[] {
  if (!Array.isArray(v)) return [];
  return v.flatMap((f): RespuestaFrase[] => {
    if (typeof f === "string") return [{ texto: f, atomos: [] }];
    if (!f || typeof f !== "object") return [];
    const o = f as Record<string, unknown>;
    return [{ texto: str(o.texto), atomos: strings(o.atomos) }];
  });
}

/** `RespuestaDoc` de `/graph`; tolera campos ausentes o de tipo equivocado. */
export function respuestasFromDocuments(docs: GraphDocument[]): Respuesta[] {
  return docs
    .filter((d) => d.model_name === RESPUESTA_MODEL)
    .map((d) => {
      const p = d.payload ?? {};
      const frases = frasesOf(p.frases);
      return {
        id: d.id,
        path: d.path,
        title: str(p.title, d.id),
        caso: str(p.caso),
        estado: str(p.estado),
        generadaPor: str(p.generada_por),
        slot: str(p.slot),
        mensaje: str(p.mensaje),
        respuesta: str(p.respuesta, frases.map((f) => f.texto).join(" ")),
        frases,
      };
    });
}

/** Resuelve una referencia de átomo: id (`c5`), gid (`AtomDoc:c5`) o ruta (`docs/atoms/c5.md`). */
export function resolveAtom(ref: string, atoms: Atom[]): Atom | undefined {
  return atoms.find((a) => a.id === ref || a.gid === ref || a.path === ref);
}

export interface FraseProvenance {
  /** Número de frase, 1-based (el `frase N` de la vista). */
  n: number;
  texto: string;
  /** Átomos resueltos, en el orden de la frase. */
  atomos: Atom[];
  /** Referencias que no corresponden a ningún átomo leído. */
  missing: string[];
}

/** Procedencia por frase: los átomos que la sostienen. */
export function respuestaProvenance(respuesta: Pick<Respuesta, "frases">, atoms: Atom[]): FraseProvenance[] {
  return respuesta.frases.map((f, i) => {
    const found: Atom[] = [];
    const missing: string[] = [];
    for (const ref of f.atomos) {
      const a = resolveAtom(ref, atoms);
      if (!a) missing.push(ref);
      else if (!found.includes(a)) found.push(a);
    }
    return { n: i + 1, texto: f.texto, atomos: found, missing };
  });
}

export interface AtomUse {
  atom: Atom;
  /** Números de frase (1-based) que lo usan; vacío = `sin usar`. */
  frases: number[];
}

export interface BaseUse {
  /** 1er segmento del tag del átomo (`programa`); `""` si no tiene tags. */
  base: string;
  title: string;
  atoms: AtomUse[];
}

/**
 * Átomos de la respuesta agrupados por base (`Base Programa (9)`), como el panel "Átomos de la
 * respuesta" de la maqueta: base = 1er segmento del PRIMER tag del átomo. Orden de bases por
 * primera aparición y, dentro de cada una, el de `slotAtomIds` (los ids del slot del que se
 * redactó; los que ninguna frase usa salen con `frases: []`). Sin `slotAtomIds`, solo los
 * átomos citados, por primera aparición en las frases.
 */
export function atomsByBase(
  respuesta: Pick<Respuesta, "frases">,
  atoms: Atom[],
  slotAtomIds?: string[],
  grupos: Pick<GroupInfo, "tag" | "title">[] = [],
): BaseUse[] {
  const prov = respuestaProvenance(respuesta, atoms);
  const uses = new Map<string, AtomUse>();
  const add = (atom: Atom) => {
    if (!uses.has(atom.id)) uses.set(atom.id, { atom, frases: [] });
    return uses.get(atom.id)!;
  };
  for (const ref of slotAtomIds ?? []) {
    const a = resolveAtom(ref, atoms);
    if (a) add(a);
  }
  for (const f of prov) for (const a of f.atomos) {
    const u = add(a);
    if (!u.frases.includes(f.n)) u.frases.push(f.n);
  }
  const groups = new Map<string, BaseUse>();
  for (const u of uses.values()) {
    const base = baseOf(u.atom.tags[0] ?? "");
    if (!groups.has(base)) groups.set(base, { base, title: base ? groupTitle(base, grupos) : "", atoms: [] });
    groups.get(base)!.atoms.push(u);
  }
  return [...groups.values()];
}

/**
 * Reglas del system prompt: los átomos que vienen de una fuente de tipo `prompt`, con las
 * frases de la respuesta que los usan (`frases: []` = no aplicada). Orden de `atoms`.
 */
export function reglasDelPrompt(respuesta: Pick<Respuesta, "frases">, atoms: Atom[], fuentes: Fuente[]): AtomUse[] {
  const prompts = new Set(fuentes.filter((f) => f.tipo === "prompt").map((f) => f.gid));
  const prov = respuestaProvenance(respuesta, atoms);
  return atoms
    .filter((a) => prompts.has(a.source))
    .map((atom) => ({ atom, frases: prov.filter((f) => f.atomos.includes(atom)).map((f) => f.n) }));
}
