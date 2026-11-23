/**
 * Registro de editores por field. La superficie no sabe cómo se edita un tipo:
 * le pregunta al registro. Otra superficie puede anteponer sus propios editores
 * (por ejemplo, un editor ProseMirror para los bloques Markdown) con `createRegistry`.
 */
import type { ComponentType } from "react";
import type { FieldSegment, SchemaField } from "../../core/contract";
import { BooleanToggle, NumberInput } from "./ScalarInputs";
import { CodeField } from "./CodeField";
import { EnumSelect } from "./EnumSelect";
import { InlineText } from "./InlineText";
import { JsonField } from "./JsonField";
import { MarkdownBlock } from "./MarkdownBlock";
import { ReadonlyField } from "./ReadonlyField";
import { TableField } from "./TableField";

export type EditorContext = "inline" | "block" | "property" | "code";

export interface FieldEditorProps {
  segment: FieldSegment;
  /** Valor tipado a editar (el `value` del segmento; si no viene, su texto). */
  value: unknown;
  schema?: SchemaField;
  context: EditorContext;
  pending: boolean;
  error?: string;
  onCommit(value: unknown): void;
}

export type FieldEditor = ComponentType<FieldEditorProps>;

export interface EditorRule {
  match(segment: FieldSegment, context: EditorContext, schema?: SchemaField): boolean;
  editor: FieldEditor;
}

export interface EditorRegistry {
  resolve(segment: FieldSegment, context: EditorContext, schema?: SchemaField): FieldEditor;
}

const isTable = (segment: FieldSegment) => segment.traits.some((t) => t === "table" || t.startsWith("table["));
const kindOf = (segment: FieldSegment, schema?: SchemaField) => segment.kind ?? schema?.kind ?? "string";

export const defaultRules: EditorRule[] = [
  { match: (s) => !s.editable, editor: ReadonlyField },
  { match: (s) => isTable(s), editor: TableField },
  { match: (s, _c, f) => kindOf(s, f) === "enum", editor: EnumSelect },
  { match: (s, _c, f) => kindOf(s, f) === "boolean", editor: BooleanToggle },
  { match: (s, _c, f) => ["integer", "number"].includes(kindOf(s, f)), editor: NumberInput },
  { match: (_s, c) => c === "code", editor: CodeField },
  { match: (s, c, f) => c === "block" && kindOf(s, f) === "string", editor: MarkdownBlock },
  { match: (s, _c, f) => ["object", "list", "unknown"].includes(kindOf(s, f)) && typeof s.value !== "string", editor: JsonField },
];

export function createRegistry(rules: EditorRule[], fallback: FieldEditor = InlineText): EditorRegistry {
  return {
    resolve(segment, context, schema) {
      return rules.find((rule) => rule.match(segment, context, schema))?.editor ?? fallback;
    },
  };
}

export const defaultEditors = createRegistry(defaultRules);
