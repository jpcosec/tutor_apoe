/** Estado de escritura del documento y conflictos con SLDB. */
import type { SaveState } from "../react/useDocumentEditor";

export function SaveStatus({ save }: { save: SaveState }) {
  const label =
    save.status === "saving" ? "Guardando…" : save.status === "saved" ? "Guardado" : save.status === "error" ? "No se guardó" : save.status === "conflict" ? "Conflicto" : "";
  return (
    <span className={`save-status save-status--${save.status}`} role="status" aria-live="polite">
      {label}
    </span>
  );
}

export function ConflictBanner({ save, onReload, onDismiss }: { save: SaveState; onReload(): void; onDismiss(): void }) {
  if (save.status === "conflict") {
    return (
      <div className="banner banner--conflict" role="alert">
        <p>
          <strong>{save.doc}</strong> cambió en SLDB desde que lo abriste; no se escribió nada. Tu valor para <code>{save.path}</code> era:
        </p>
        <pre>{typeof save.value === "string" ? save.value : JSON.stringify(save.value, null, 2)}</pre>
        <div className="banner__actions">
          <button type="button" className="btn btn--primary" onClick={onReload}>
            Recargar documento
          </button>
          <button type="button" className="btn" onClick={onDismiss}>
            Cerrar
          </button>
        </div>
      </div>
    );
  }
  if (save.status === "error") {
    return (
      <div className="banner banner--error" role="alert">
        <p>{save.message}</p>
        <button type="button" className="btn" onClick={onDismiss}>
          Cerrar
        </button>
      </div>
    );
  }
  return null;
}
