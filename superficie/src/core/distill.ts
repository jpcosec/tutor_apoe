/**
 * DESTILACIÓN · anchors → regularidad → modelo (§16.1).
 *
 * "El modelo no se escribe, se destila." Esta capa NO escribe nada: detecta anchors
 * que apuntan al mismo referente, los agrupa y propone campos. El modelo lo revisa y
 * lo escribe una persona.
 *
 * El TIPO de un anchor no vive en un campo `kind`: este store registra `AnchorDoc`
 * con `symbol`/`forms`/`ref`/`steps`/`motive`. El tipo está DENTRO de `ref`, que es
 * una s-expression tipada — el primer átomo es el tipo:
 *
 *   (model M) · (field M f) · (where M "pred") · (relation R) · (doc "M:name")
 *   (change (it "it" M) f "v") · (move (create M) (assert R ...) ...)
 *
 * También se leen los refs viejos en string: `model:M`, `predicate:M:<pred>`,
 * `action:change M.f=v`, `compose`.
 *
 * DEDUPLICACIÓN: cada campo propuesto se compara (`GET /corpus/rank?fields=1`) contra los
 * campos que ya existen en el store. Acá vive la lógica pura (armar la consulta y el
 * `among`, clasificar duplicado/parecido, excluir a los propios anchors); la vista hace la
 * llamada y muestra los tres estados. Es informativo: no cambia lo que se propone. El
 * texto que se compara es el `motive` (la razón escrita), único texto que trae la
 * propuesta; el índice mide parecido de TEXTO (difflib), no de significado.
 *
 * Regla dura: un campo sin `motive` no se propone. El motive es lo que hace auditable
 * la destilación; sin razón escrita, no hay campo.
 */
import type { FieldRankHit, GraphDocument, RankParams } from "./contract";
import { above, byScore, DUPLICATE_THRESHOLD, queryText, SUGGEST_THRESHOLD } from "./similarity";

export type RefKind = "model" | "field" | "where" | "relation" | "doc" | "change" | "move" | "other";

/** Un `ref` desarmado en tipo + referente. El tipo sale del primer átomo. */
export interface RefParts {
  kind: RefKind;
  raw: string;
  model?: string;
  field?: string;
  relation?: string;
  predicate?: string;
}

/** Lo mínimo que un anchor aporta a la destilación, leído de su payload. */
export interface AnchorEntry {
  doc: string;
  symbol: string;
  ref: string;
  motive: string;
}

export type ProposedRole = "field" | "reference" | "predicate";

export interface ProposalSource {
  doc: string;
  symbol: string;
  motive: string;
  ref: string;
}

export interface ProposedField {
  /** Campo de M (`field`), tipo de relación (`reference`) o predicado (`predicate`). */
  name: string;
  role: ProposedRole;
  symbol: string;
  motive: string;
  ref: string;
  /** Todos los anchors que apuntan a esto; el primero es el que presta el motive. */
  sources: ProposalSource[];
}

export interface ModelDraft {
  /** Modelo objetivo del ref (para `(relation R)`, el nombre de la relación). */
  model: string;
  fields: ProposedField[];
  /** Candidatos a `__references__` / `__containment__`. */
  references: ProposedField[];
  /** Predicados: NO son campos. */
  predicates: ProposedField[];
  /** Borrador de `__template__`, solo si hay campos suficientes. */
  template: string | null;
}

export interface DistillResult {
  models: ModelDraft[];
  /** Anchors cuyo `ref` no se pudo tipar. */
  unparsed: AnchorEntry[];
  /** Anchors tipados pero sin `motive`: no se proponen, no son auditables. */
  unbacked: AnchorEntry[];
}

const QUOTES = /^["']|["']$/g;

function clean(token: string | undefined): string | undefined {
  const value = token?.replace(QUOTES, "").trim();
  return value ? value : undefined;
}

/** Átomos de una s-expression, sin paréntesis y con las comillas sacadas. */
function atoms(expression: string): string[] {
  const list: string[] = [];
  let current = "";
  let quoted = false;
  for (const char of expression) {
    if (char === '"') {
      quoted = !quoted;
      current += char;
      continue;
    }
    if (!quoted && (char === "(" || char === ")")) {
      if (current.trim()) list.push(current.trim());
      current = "";
      continue;
    }
    if (!quoted && /\s/.test(char)) {
      if (current.trim()) list.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }
  if (current.trim()) list.push(current.trim());
  return list.map((atom) => atom.replace(QUOTES, ""));
}

/** `(change (it "it" M) f "v")` → modelo y campo. */
function parseChange(expression: string): Pick<RefParts, "model" | "field"> {
  const match = /\(it\s+"it"\s+([^\s)]+)\)\s+([^\s)]+)/.exec(expression);
  if (!match) return {};
  return { model: match[1], field: match[2] };
}

/** `(move (create M) …)` → modelo. */
function parseMove(expression: string): Pick<RefParts, "model"> {
  const match = /\(create\s+([^\s)]+)\)/.exec(expression);
  return match?.[1] ? { model: match[1] } : {};
}

function parseRefString(ref: string): RefParts | null {
  const model = /^model:([^\s]+)$/.exec(ref);
  if (model?.[1]) return { kind: "model", model: model[1], raw: ref };
  const predicate = /^predicate:([^:\s]+):(.+)$/.exec(ref);
  if (predicate?.[1] && predicate[2]) return { kind: "where", model: predicate[1], predicate: predicate[2], raw: ref };
  const field = /^field:([^.]+)\.(.+)$/.exec(ref);
  if (field?.[1] && field[2]) return { kind: "field", model: field[1], field: field[2], raw: ref };
  const relation = /^relation:([^\s]+)$/.exec(ref);
  if (relation?.[1]) return { kind: "relation", relation: relation[1], raw: ref };
  const doc = /^doc:([^:\s]+):.+$/.exec(ref);
  if (doc?.[1]) return { kind: "doc", model: doc[1], raw: ref };
  const change = /^action:change\s+([^.]+)\.([^=\s]+)=/.exec(ref);
  if (change?.[1] && change[2]) return { kind: "change", model: change[1], field: change[2], raw: ref };
  return null;
}

/**
 * Desarma un `ref` en tipo + referente. Soporta la s-expression y los refs viejos en
 * string; lo que no reconoce cae en `kind: "other"`.
 */
export function parseRef(ref: string): RefParts | null {
  const raw = ref.trim();
  if (!raw) return null;
  if (raw.startsWith("(")) {
    const list = atoms(raw);
    const head = list[0]?.toLowerCase() ?? "";
    const first = clean(list[1]);
    if (head === "model") return first ? { kind: "model", model: first, raw } : { kind: "other", raw };
    if (head === "field") return first ? { kind: "field", model: first, field: clean(list[2]), raw } : { kind: "other", raw };
    if (head === "where") return first ? { kind: "where", model: first, predicate: clean(list[2]), raw } : { kind: "other", raw };
    if (head === "relation") return first ? { kind: "relation", relation: first, raw } : { kind: "other", raw };
    if (head === "doc") return { kind: "doc", model: first?.split(":")[0], raw };
    if (head === "change") return { kind: "change", ...parseChange(raw), raw };
    if (head === "move") return { kind: "move", ...parseMove(raw), raw };
    return { kind: "other", raw };
  }
  return parseRefString(raw) ?? { kind: "other", raw };
}

function targetOf(parts: RefParts): string | undefined {
  if (parts.kind === "relation") return parts.relation;
  return parts.model;
}

function roleOf(kind: RefKind): ProposedRole | null {
  if (kind === "field") return "field";
  if (kind === "relation") return "reference";
  if (kind === "where") return "predicate";
  return null;
}

function nameOf(parts: RefParts, role: ProposedRole): string | undefined {
  if (role === "field") return parts.field;
  if (role === "reference") return parts.relation;
  return parts.predicate;
}

function textOf(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

/**
 * Los documentos que son anchors. Con `modelId` se filtra por el modelo que registra
 * el store (el que resuelve `findAnchorModel`); sin él, por nombre de modelo.
 */
export function collectAnchors(docs: GraphDocument[], modelId: string | null): AnchorEntry[] {
  const entries: AnchorEntry[] = [];
  for (const doc of docs) {
    const matches = modelId ? doc.model_name === modelId : /anchor/i.test(doc.model_name);
    if (!matches) continue;
    const ref = textOf(doc.payload.ref);
    if (!ref) continue;
    entries.push({ doc: doc.id, symbol: textOf(doc.payload.symbol), ref, motive: textOf(doc.payload.motive) });
  }
  return entries;
}

/**
 * Borrador de `__template__`: los campos propuestos como posiciones del frontmatter.
 *
 * Un anchor no guarda posición, así que "posición estable" no es observable desde acá;
 * el proxy que sí es observable es que el modelo tenga DOS o más campos distintos. Con
 * menos que eso no se propone template (y el cuerpo lo escribe la persona).
 */
export function suggestTemplate(fields: ProposedField[]): string | null {
  if (fields.length < 2) return null;
  const lines = fields.map((field) => `${field.name}: \u2e22rev\u2022${field.name}\u2e25`);
  return ["---", ...lines, "---", ""].join("\n");
}

/** Agrupa por modelo objetivo y propone campos, referencias y predicados. */
export function distill(entries: AnchorEntry[]): DistillResult {
  const groups = new Map<string, ModelDraft>();
  const unparsed: AnchorEntry[] = [];
  const unbacked: AnchorEntry[] = [];

  for (const entry of entries) {
    const parts = parseRef(entry.ref);
    if (!parts || parts.kind === "other") {
      unparsed.push(entry);
      continue;
    }
    const target = targetOf(parts);
    if (!target) {
      unparsed.push(entry);
      continue;
    }
    const role = roleOf(parts.kind);
    if (!role) continue; // model/doc/change/move: tipan pero no proponen campo.
    const motive = entry.motive.trim();
    if (!motive) {
      unbacked.push(entry);
      continue;
    }
    const name = nameOf(parts, role);
    if (!name) {
      unparsed.push(entry);
      continue;
    }

    const draft = groups.get(target) ?? { model: target, fields: [], references: [], predicates: [], template: null };
    const bucket = role === "field" ? draft.fields : role === "reference" ? draft.references : draft.predicates;
    const source: ProposalSource = { doc: entry.doc, symbol: entry.symbol, motive, ref: entry.ref };
    const existing = bucket.find((proposal) => proposal.name === name);
    if (existing) {
      existing.sources.push(source);
    } else {
      bucket.push({ name, role, symbol: entry.symbol, motive, ref: entry.ref, sources: [source] });
    }
    groups.set(target, draft);
  }

  const byWeight = (a: ProposedField, b: ProposedField) => b.sources.length - a.sources.length || a.name.localeCompare(b.name);
  const models = [...groups.values()]
    .map((draft) => ({
      ...draft,
      fields: [...draft.fields].sort(byWeight),
      references: [...draft.references].sort(byWeight),
      predicates: [...draft.predicates].sort(byWeight),
    }))
    .filter((draft) => draft.fields.length + draft.references.length + draft.predicates.length > 0)
    .map((draft) => ({ ...draft, template: suggestTemplate(draft.fields) }))
    .sort((a, b) => b.fields.length - a.fields.length || a.model.localeCompare(b.model));

  return { models, unparsed, unbacked };
}

/** Vecinos que se piden por campo. */
export const SIMILAR_K = 2;
/** Si el `among` no entra en la URL se consulta sin él, pidiendo más para poder filtrar. */
export const AMONG_MAX_CHARS = 3000;
export const SIMILAR_K_UNSCOPED = 8;

/** Texto a comparar de un campo propuesto; `null` si no tiene (no se consulta). */
export function similarityQuery(proposal: Pick<ProposedField, "motive">): string | null {
  return queryText(proposal.motive) || null;
}

/**
 * Ids (`Model:name`, como pide `among`) de los documentos con los que comparar: todos menos
 * los anchors que se están destilando, para que un campo no se marque duplicado de sí mismo.
 */
export function amongIds(docs: GraphDocument[], anchors: AnchorEntry[]): string[] {
  const own = new Set(anchors.map((anchor) => anchor.doc));
  return docs.filter((doc) => !own.has(doc.id)).map((doc) => `${doc.model_name}:${doc.id}`);
}

/** Parámetros de `rank` para una consulta; sin `among` si no entra o si no queda nada. */
export function rankRequest(q: string, among: string[]): RankParams & { fields: true } {
  const scoped = among.length > 0 && among.join(",").length <= AMONG_MAX_CHARS;
  return {
    q,
    fields: true,
    k: scoped ? SIMILAR_K : SIMILAR_K_UNSCOPED,
    threshold: SUGGEST_THRESHOLD,
    ...(scoped ? { among } : {}),
  };
}

export interface FieldMatch {
  kind: "duplicate" | "similar";
  hit: FieldRankHit;
}

/**
 * Hits de un campo propuesto: sin los propios anchors, con puntaje suficiente, mejores
 * primero y a lo sumo `SIMILAR_K`. Lista vacía = "Sin campos parecidos".
 */
export function classifyMatches(hits: FieldRankHit[], ownDocs: ReadonlySet<string>): FieldMatch[] {
  const foreign = hits.filter((hit) => !ownDocs.has(hit.name));
  return above(byScore(foreign), SUGGEST_THRESHOLD)
    .slice(0, SIMILAR_K)
    .map((hit) => ({ kind: hit.score >= DUPLICATE_THRESHOLD ? "duplicate" : "similar", hit }));
}

/** Clave estable de un campo propuesto dentro de su modelo, para el estado y el caché. */
export const proposalKey = (model: string, proposal: Pick<ProposedField, "name" | "role">): string => `${model}\u0000${proposal.role}\u0000${proposal.name}`;
