/**
 * Direcciones de field (`tags/0`, `steps/2/title`) sobre un payload, sin mutarlo.
 * Es el mismo espacio de direcciones que `sldb fields`.
 */
import type { Payload } from "./contract";

export type PathPart = string | number;

export function parsePath(path: string): PathPart[] {
  return path
    .split("/")
    .filter((part) => part.length > 0)
    .map((part) => (/^\d+$/.test(part) ? Number(part) : part));
}

export function rootOf(path: string): string {
  return parsePath(path).find((p): p is string => typeof p === "string") ?? path;
}

export function getAt(value: unknown, path: string): unknown {
  let current: unknown = value;
  for (const part of parsePath(path)) {
    if (current === null || typeof current !== "object") return undefined;
    current = (current as Record<PathPart, unknown>)[part];
  }
  return current;
}

function setIn(container: unknown, parts: PathPart[], next: unknown): unknown {
  const [head, ...rest] = parts;
  if (head === undefined) return next;
  const child = setIn(
    container !== null && typeof container === "object" ? (container as Record<PathPart, unknown>)[head] : undefined,
    rest,
    next,
  );
  if (typeof head === "number") {
    const list = Array.isArray(container) ? [...container] : [];
    list[head] = child;
    return list;
  }
  const record = container !== null && typeof container === "object" && !Array.isArray(container) ? container : {};
  return { ...(record as Record<string, unknown>), [head]: child };
}

export function setAt(payload: Payload, path: string, next: unknown): Payload {
  return setIn(payload, parsePath(path), next) as Payload;
}

function listAt(payload: Payload, listPath: string): unknown[] {
  const current = getAt(payload, listPath);
  return Array.isArray(current) ? current : [];
}

export function insertAt(payload: Payload, listPath: string, index: number, item: unknown): Payload {
  const list = [...listAt(payload, listPath)];
  list.splice(Math.max(0, Math.min(index, list.length)), 0, item);
  return setAt(payload, listPath, list);
}

export function removeAt(payload: Payload, listPath: string, index: number): Payload {
  return setAt(payload, listPath, listAt(payload, listPath).filter((_, i) => i !== index));
}

export function moveAt(payload: Payload, listPath: string, from: number, to: number): Payload {
  const list = [...listAt(payload, listPath)];
  const [item] = list.splice(from, 1);
  if (item === undefined) return payload;
  list.splice(to, 0, item);
  return setAt(payload, listPath, list);
}

/** `tags/3` → `{ list: "tags", index: 3 }`; cualquier otra cosa → null. */
export function listItemOf(path: string): { list: string; index: number } | null {
  const match = /^(.*)\/(\d+)$/.exec(path);
  if (!match || !match[1]) return null;
  return { list: match[1], index: Number(match[2]) };
}
