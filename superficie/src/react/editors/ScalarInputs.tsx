/** Números y booleanos: se guardan con su tipo, no como texto. */
import type { FieldEditorProps } from "./registry";

export function NumberInput({ segment, value, schema, pending, onCommit }: FieldEditorProps) {
  const integer = (segment.kind ?? schema?.kind) === "integer";
  return (
    <input
      className="field-number"
      type="number"
      step={integer ? 1 : "any"}
      aria-label={segment.path}
      defaultValue={value === null || value === undefined ? "" : String(value)}
      disabled={pending}
      onBlur={(event) => {
        const next = event.target.value === "" ? null : integer ? parseInt(event.target.value, 10) : Number(event.target.value);
        if (next !== value) onCommit(next);
      }}
    />
  );
}

export function BooleanToggle({ segment, value, pending, onCommit }: FieldEditorProps) {
  return (
    <label className="field-bool">
      <input type="checkbox" aria-label={segment.path} checked={value === true} disabled={pending} onChange={(e) => onCommit(e.target.checked)} />
      <span>{value === true ? "sí" : "no"}</span>
    </label>
  );
}
