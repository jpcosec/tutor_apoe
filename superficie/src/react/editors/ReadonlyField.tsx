/** Fields `render`/`py`: se muestran, no se editan (lo dicta el template, no la UI). */
import type { FieldEditorProps } from "./registry";

export function ReadonlyField({ segment, context }: FieldEditorProps) {
  const Tag = context === "block" ? "div" : "span";
  return (
    <Tag className={`field-readonly field-readonly--${context}`} title={`${segment.path}: se calcula al renderizar`}>
      {segment.text}
    </Tag>
  );
}
