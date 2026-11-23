/**
 * Field de texto inline. Se edita en el lugar (contentEditable en texto plano):
 * Enter guarda, Escape descarta. El DOM se resincroniza con el valor solo fuera de foco.
 */
import { useEffect, useRef, type KeyboardEvent } from "react";
import type { FieldEditorProps } from "./registry";

export function InlineText({ segment, value, schema, pending, error, onCommit }: FieldEditorProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const current = value === null || value === undefined ? "" : String(value);

  useEffect(() => {
    const node = ref.current;
    if (node && document.activeElement !== node) node.textContent = current;
  }, [current]);

  const commit = () => {
    const next = ref.current?.textContent ?? "";
    if (next !== current) onCommit(next);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLSpanElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      ref.current?.blur();
    } else if (event.key === "Escape") {
      if (ref.current) ref.current.textContent = current;
      ref.current?.blur();
    }
  };

  return (
    <span
      ref={ref}
      className="field-inline"
      contentEditable="plaintext-only"
      suppressContentEditableWarning
      role="textbox"
      aria-label={segment.path}
      aria-invalid={error ? true : undefined}
      data-pending={pending || undefined}
      data-placeholder={schema?.description ?? segment.path}
      title={schema?.description}
      spellCheck
      onBlur={commit}
      onKeyDown={onKeyDown}
    />
  );
}
