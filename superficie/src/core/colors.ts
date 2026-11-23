/**
 * Un color por field raíz, asignado por orden de aparición: estable dentro de un
 * documento y distinto entre fields vecinos. Los ítems de lista heredan el de su raíz.
 */
import { rootOf } from "./paths";

export const FIELD_PALETTE_SIZE = 10;

export class FieldColors {
  private readonly slots = new Map<string, number>();

  constructor(keys: Iterable<string> = []) {
    for (const key of keys) this.slotOf(key);
  }

  slotOf(key: string): number {
    const existing = this.slots.get(key);
    if (existing !== undefined) return existing;
    const slot = this.slots.size % FIELD_PALETTE_SIZE;
    this.slots.set(key, slot);
    return slot;
  }

  /** Clave de color: fields propios por raíz; fields de otro documento por `doc#raíz`. */
  static keyFor(path: string, sourceDoc?: string | null): string {
    const root = rootOf(path);
    return sourceDoc ? `${sourceDoc}#${root}` : root;
  }
}
