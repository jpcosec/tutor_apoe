/** Fields estructurados sin editor propio: se editan como JSON y se validan al guardar. */
import { useState } from "react";
import type { FieldEditorProps } from "./registry";
import { CodeEditor } from "./CodeEditor";

export function JsonField({ segment, value, pending, onCommit }: FieldEditorProps) {
  const [editing, setEditing] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const source = JSON.stringify(value ?? null, null, 2);
  if (editing) {
    return (
      <div className="field-block field-block--editing">
        <CodeEditor
          initial={source}
          language="plain"
          onCancel={() => setEditing(false)}
          onSave={(next) => {
            try {
              const parsed: unknown = JSON.parse(next);
              setEditing(false);
              setProblem(null);
              if (next !== source) onCommit(parsed);
            } catch (error) {
              setProblem(`JSON inválido: ${(error as Error).message}`);
            }
          }}
        />
        {problem && <p className="field-error">{problem}</p>}
      </div>
    );
  }
  return (
    <pre className="field-json" role="button" tabIndex={0} data-pending={pending || undefined} aria-label={`Editar ${segment.path}`} onClick={() => setEditing(true)}>
      {segment.text || source}
    </pre>
  );
}
