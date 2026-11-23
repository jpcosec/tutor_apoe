/**
 * Tema de la superficie: `auto` sigue al sistema (`prefers-color-scheme`), `light`
 * y `dark` lo fuerzan. El valor vive en `data-theme` del <html> — el CSS hace todo
 * el trabajo — y se persiste en localStorage. No hay colores en JS.
 */

export const THEMES = ["auto", "light", "dark"] as const;
export type Theme = (typeof THEMES)[number];

export const THEME_STORAGE_KEY = "sldb.theme";
export const DEFAULT_THEME: Theme = "auto";

function isTheme(value: unknown): value is Theme {
  return typeof value === "string" && (THEMES as readonly string[]).includes(value);
}

/** Lee el tema guardado. Si falta o es basura, `auto`. */
export function readTheme(): Theme {
  let stored: string | null = null;
  try {
    stored = localStorage.getItem(THEME_STORAGE_KEY);
  } catch {
    // localStorage puede estar bloqueado (modo privado): el default alcanza.
  }
  return isTheme(stored) ? stored : DEFAULT_THEME;
}

/** Escribe `data-theme` en <html>. Es lo único que el CSS observa. */
export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
}

/** Persiste y aplica. */
export function storeTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Sin persistencia el tema vale para esta sesión y no rompe nada.
  }
  applyTheme(theme);
}

/** Aplica el tema guardado al arrancar, antes del primer render. */
export function initTheme(): Theme {
  const theme = readTheme();
  applyTheme(theme);
  return theme;
}
