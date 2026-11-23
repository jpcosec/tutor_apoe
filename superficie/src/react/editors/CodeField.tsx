/** Field dentro de un bloque de código (p. ej. un diagrama): se edita como texto plano. */
import { useState } from "react";
import type { FieldEditorProps } from "./registry";
import { CodeEditor } from "./CodeEditor";

export function CodeField({ segment, value, pending, onCommit }: FieldEditorProps) {
  const [editing, setEditing] = useState(false);
  const source = value === null || value === undefined ? "" : String(value);
  if (editing) {
    return (
      <CodeEditor
        initial={source}
        language="plain"
        onCancel={() => setEditing(false)}
        onSave={(next) => {
          setEditing(false);
          if (next !== source) onCommit(next);
        }}
      />
    );
  }
  return (
    <code
      className="field-code"
      role="button"
      tabIndex={0}
      aria-label={`Editar ${segment.path}`}
      data-pending={pending || undefined}
      onClick={() => setEditing(true)}
      onKeyDown={(e) => e.key === "Enter" && setEditing(true)}
    >
      {source || " "}
    </code>
  );
}
