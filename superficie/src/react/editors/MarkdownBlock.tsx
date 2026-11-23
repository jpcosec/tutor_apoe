/**
 * Field de bloque en Markdown. Se ve renderizado; al editar se abre su fuente en
 * CodeMirror. Así lo que no se toca no se re-serializa: se guarda exactamente el
 * texto que quedó en el editor.
 */
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { FieldEditorProps } from "./registry";
import { CodeEditor } from "./CodeEditor";

export function MarkdownBlock({ segment, value, schema, pending, error, onCommit }: FieldEditorProps) {
  const [editing, setEditing] = useState(false);
  const source = value === null || value === undefined ? "" : String(value);

  if (editing) {
    return (
      <div className="field-block field-block--editing">
        <CodeEditor
          initial={source}
          placeholder={schema?.description}
          onCancel={() => setEditing(false)}
          onSave={(next) => {
            setEditing(false);
            if (next !== source) onCommit(next);
          }}
        />
      </div>
    );
  }

  return (
    <div
      className="field-block"
      role="button"
      tabIndex={0}
      aria-label={`Editar ${segment.path}`}
      data-pending={pending || undefined}
      aria-invalid={error ? true : undefined}
      title={schema?.description}
      onClick={() => setEditing(true)}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          setEditing(true);
        }
      }}
    >
      {source.trim() ? (
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{source}</ReactMarkdown>
      ) : (
        <p className="field-block__empty">{schema?.description ?? "Vacío. Haz clic para escribir."}</p>
      )}
    </div>
  );
}
