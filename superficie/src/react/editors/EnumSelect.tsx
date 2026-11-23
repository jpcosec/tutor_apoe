/** Enum como selector: solo ofrece los valores que acepta el modelo. */
import type { FieldEditorProps } from "./registry";

export function EnumSelect({ segment, value, schema, pending, onCommit }: FieldEditorProps) {
  const options = (schema?.enum ?? [value]).map(String);
  const current = value === null || value === undefined ? "" : String(value);
  return (
    <select
      className="field-enum"
      aria-label={segment.path}
      value={current}
      disabled={pending}
      title={schema?.description}
      onChange={(event) => event.target.value !== current && onCommit(event.target.value)}
    >
      {!options.includes(current) && <option value={current}>{current || "—"}</option>}
      {options.map((option) => (
        <option key={option} value={option}>
          {option}
        </option>
      ))}
    </select>
  );
}
