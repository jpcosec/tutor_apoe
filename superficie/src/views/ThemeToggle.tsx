/** Tema de la hoja: automático (el del sistema), claro u oscuro. */
import { useState } from "react";
import { readTheme, storeTheme, THEMES, type Theme } from "../core/theme";

const LABEL: Record<Theme, string> = { auto: "Auto", light: "Claro", dark: "Oscuro" };

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readTheme);

  function choose(next: Theme) {
    storeTheme(next);
    setTheme(next);
  }

  return (
    <div className="theme-toggle" role="group" aria-label="Tema">
      {THEMES.map((option) => (
        <button
          key={option}
          type="button"
          className={`theme-toggle__btn${option === theme ? " is-active" : ""}`}
          aria-pressed={option === theme}
          onClick={() => choose(option)}
        >
          {LABEL[option]}
        </button>
      ))}
    </div>
  );
}
