/**
 * GRUPOS COMO DOCUMENTO · mapeo puro tag <-> `GrupoDoc`.
 *
 * Un grupo (tag con puntos: `infra.ingesta`) es un documento `GrupoDoc` cuyo nombre es el
 * SLUG del tag. Una relación sobre un grupo es un `RelationDoc` normal con `GrupoDoc:<slug>`
 * en `source_id` o `target_id`; la heredan todos los átomos del grupo y de sus subgrupos.
 *
 * Slug: los puntos pasan a guiones (`infra.ingesta` -> `infra-ingesta`) y cualquier otro
 * carácter que no sea letra, dígito, `_` o `-` pasa a `_` (un nombre de documento no admite
 * `:` ni `/`). El mapeo es con pérdida (`a-b` y `a.b` dan el mismo slug), por eso el sentido
 * inverso (`tagOfGroupGid`) resuelve contra los tags conocidos, no invierte el texto.
 * Sin dependencias: no importa otros módulos del core.
 */

export const GROUP_MODEL = "GrupoDoc";

/** Nombre de documento del grupo `tag`. */
export function groupSlug(tag: string): string {
  return tag
    .trim()
    .split(".")
    .filter(Boolean)
    .join("-")
    .replace(/[^\p{L}\p{N}_-]/gu, "_");
}

/** Id de documento (`GrupoDoc:infra-ingesta`), el que llevan las aristas. */
export function groupGid(tag: string): string {
  return `${GROUP_MODEL}:${groupSlug(tag)}`;
}

export const isGroupGid = (id: string): boolean => id.startsWith(`${GROUP_MODEL}:`);

/** Slug de un `GrupoDoc:<slug>`, o `null` si no lo es. */
export function slugOfGroupGid(id: string): string | null {
  return isGroupGid(id) ? id.slice(GROUP_MODEL.length + 1) : null;
}

/**
 * Tag de un `GrupoDoc:<slug>` buscando entre `knownTags` (los tags de los átomos y de los
 * `GrupoDoc`), incluidos los prefijos (`infra` sale de `infra.ingesta`). Si dos tags comparten
 * slug gana el primero; sin coincidencia devuelve el slug tal cual.
 */
export function tagOfGroupGid(id: string, knownTags: Iterable<string>): string | null {
  const slug = slugOfGroupGid(id);
  if (slug === null) return null;
  for (const tag of knownTags) {
    const parts = tag.split(".").filter(Boolean);
    for (let i = 1; i <= parts.length; i++) {
      const prefix = parts.slice(0, i).join(".");
      if (groupSlug(prefix) === slug) return prefix;
    }
  }
  return slug;
}

/** Payload de un `GrupoDoc` nuevo para el grupo `tag`. */
export function groupPayload(tag: string): { title: string; tag: string; description: string } {
  return { title: tag, tag, description: "" };
}

export interface GroupDocRef {
  id: string;
  gid: string;
  tag: string;
}

/** `GrupoDoc` de `/graph` reducidos a lo que la vista necesita. */
export function groupsFromDocuments(docs: { id: string; model_name: string; payload: Record<string, unknown> }[]): GroupDocRef[] {
  return docs
    .filter((d) => d.model_name === GROUP_MODEL)
    .map((d) => ({ id: d.id, gid: `${GROUP_MODEL}:${d.id}`, tag: typeof d.payload.tag === "string" && d.payload.tag ? d.payload.tag : d.id }));
}

/** `GrupoDoc` con lo que la vista necesita para mostrarlo: además de `GroupDocRef`, título y descripción. */
export interface GroupInfo extends GroupDocRef {
  /** Título de DISPLAY del `GrupoDoc` (`Asistente`); `""` si no trae. */
  title: string;
  description: string;
}

/** Como `groupsFromDocuments` pero con `title` y `description` (`GroupInfo`). */
export function groupInfosFromDocuments(docs: { id: string; model_name: string; payload: Record<string, unknown> }[]): GroupInfo[] {
  const byId = new Map(docs.map((d) => [d.id, d]));
  return groupsFromDocuments(docs).map((g) => {
    const p = byId.get(g.id)?.payload ?? {};
    return { ...g, title: typeof p.title === "string" ? p.title : "", description: typeof p.description === "string" ? p.description : "" };
  });
}

/** ¿Un error de creación es «ya existe» (409)? */
export const isAlreadyExists = (err: unknown): boolean => (err as { status?: number } | null)?.status === 409;
