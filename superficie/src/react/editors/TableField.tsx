/**
 * Field de tabla (`rev,table[...]`): lista de filas editable celda por celda.
 * Las columnas salen del marcador; si no las declara, de la primera fila.
 */
import type { FieldEditorProps } from "./registry";

type Row = Record<string, unknown>;

function columnsOf(traits: string[], rows: Row[]): string[] {
  const declared = traits.find((t) => t.startsWith("table["));
  if (declared) return declared.slice(6, -1).split(",").map((c) => c.trim()).filter(Boolean);
  return rows[0] ? Object.keys(rows[0]) : [];
}

export function TableField({ segment, value, pending, onCommit }: FieldEditorProps) {
  const rows: Row[] = Array.isArray(value) ? (value as Row[]) : [];
  const columns = columnsOf(segment.traits, rows);
  const update = (index: number, column: string, cell: string) => {
    if (String(rows[index]?.[column] ?? "") === cell) return;
    onCommit(rows.map((row, i) => (i === index ? { ...row, [column]: cell } : row)));
  };
  const addRow = () => onCommit([...rows, Object.fromEntries(columns.map((c) => [c, ""]))]);
  const removeRow = (index: number) => onCommit(rows.filter((_, i) => i !== index));

  return (
    <div className="field-table" data-pending={pending || undefined}>
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c} scope="col">
                {c}
              </th>
            ))}
            <th aria-label="Acciones" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((c) => (
                <td key={c}>
                  <input
                    aria-label={`${segment.path} fila ${index + 1} ${c}`}
                    defaultValue={String(row[c] ?? "")}
                    onBlur={(e) => update(index, c, e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
                  />
                </td>
              ))}
              <td className="field-table__actions">
                <button type="button" className="icon-btn" aria-label={`Quitar fila ${index + 1}`} onClick={() => removeRow(index)}>
                  ×
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button type="button" className="add-btn" onClick={addRow} disabled={columns.length === 0}>
        + fila
      </button>
    </div>
  );
}
