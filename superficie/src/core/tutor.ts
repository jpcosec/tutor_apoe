/**
 * Lo propio del Tutor APOE en esta copia de la superficie: qué tipos de página son la
 * configuración del tutor y cómo se nombran, para personas, las carpetas de su base.
 *
 * `CONFIG_MODELS` tiene que calzar con `CONFIG_MODELS` de `src/tutor/wiki.py`: el servidor rechaza
 * cualquier guardado sobre otro tipo, así que un tipo que falte allá se vería editable y no guardaría.
 */

/** Los tipos de página que se editan aquí. El resto de la base se genera desde `desk/atoms/`. */
export const CONFIG_MODELS: readonly string[] = ["AgentDoc"];

/** Rótulo de cada carpeta de la base (`kbs/<kb>/<carpeta>/`) en el índice. */
export const GROUP_LABELS: Record<string, string> = {
  agent: "Configuración del tutor",
  knowledge: "Átomos de conocimiento",
  sources: "Átomos sobre la fuente",
  taxonomy: "Ramas",
  relations: "Relaciones",
  categories: "Categorías de tags",
  projections: "Proyecciones",
  ingest: "Fuentes y fragmentos",
  proposed: "Átomos propuestos",
  kgdb: "Tipos de relación",
  sldb: "Tipos de relación de sldb",
};

/** Por qué una página generada no se edita aquí, y dónde se cambia. */
export const SOLO_LECTURA =
  "Esta página se genera desde los átomos fuente (desk/atoms/): aquí se lee. Para cambiarla, se edita el átomo fuente (con deskops) y se regenera la base.";
