/**
 * Leyenda de fields del documento: color, tipo y descripción del contrato.
 * Pasar el cursor por un field lo destaca en la página. Los opcionales ausentes se pueden agregar.
 */
import { useState } from "react";
import type { FieldSegment, SchemaField, Segment } from "../core/contract";
import { FieldColors } from "../core/colors";
import { fieldRoots, topLevelFields } from "../core/layout";
import { rootOf } from "../core/paths";

interface LegendProps {
  segments: Segment[];
  colors: FieldColors;
  fields: SchemaField[];
  onHighlight(key: string | null): void;
  onAdd?(field: SchemaField, value: unknown): void;
}

const MARKER_LABEL: Record<string, string> = { rev: "editable", optrev: "opcional", render: "calculado", py: "calculado" };

export function Legend({ segments, colors, fields, onHighlight, onAdd }: LegendProps) {
  const present = fieldRoots(segments);
  const bySegment = new Map<string, FieldSegment>();
  for (const f of topLevelFields(segments)) if (!bySegment.has(rootOf(f.path))) bySegment.set(rootOf(f.path), f);
  const missing = fields.filter((f) => !present.includes(f.name) && !f.required);

  return (
    <section className="legend" aria-label="Fields del documento">
      <h2 className="panel-title">Fields</h2>
      <ul>
        {present.map((root) => {
          const segment = bySegment.get(root);
          const schema = fields.find((f) => f.name === root);
          return (
            <li key={root} className={`legend__row f-${colors.slotOf(root)}`} onMouseEnter={() => onHighlight(root)} onMouseLeave={() => onHighlight(null)}>
              <span className="legend__swatch" aria-hidden />
              <span className="legend__name">{root}</span>
              <span className="legend__meta">
                {schema?.kind ?? segment?.kind ?? "?"} · {MARKER_LABEL[segment?.marker ?? ""] ?? segment?.marker}
              </span>
              {schema?.description && <span className="legend__desc">{schema.description}</span>}
            </li>
          );
        })}
      </ul>
      {missing.length > 0 && onAdd && (
        <>
          <h3 className="panel-subtitle">Sin completar</h3>
          <ul>
            {missing.map((field) => (
              <MissingField key={field.name} field={field} onAdd={onAdd} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function MissingField({ field, onAdd }: { field: SchemaField; onAdd(field: SchemaField, value: unknown): void }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="legend__missing">
      <span className="legend__name">{field.name}</span>
      {field.description && <span className="legend__desc">{field.description}</span>}
      {open ? (
        <input
          autoFocus
          className="add-input"
          aria-label={`Valor para ${field.name}`}
          onBlur={() => setOpen(false)}
          onKeyDown={(e) => {
            const text = e.currentTarget.value.trim();
            if (e.key === "Escape") setOpen(false);
            if (e.key === "Enter" && text) onAdd(field, field.kind === "stringlist" ? [text] : text);
          }}
        />
      ) : (
        <button type="button" className="add-btn" onClick={() => setOpen(true)}>
          + completar
        </button>
      )}
    </li>
  );
}
