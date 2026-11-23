/**
 * Superficie de documento: dibuja la secuencia de segmentos de SLDB.
 * El texto del template es fijo; cada field se pinta con su color y se edita con el
 * editor que diga el registro. Las piezas compuestas se dibujan recursivamente y
 * escriben en su documento de origen.
 */
import { useState, type ReactNode } from "react";
import type { CompositionPiece, FieldSegment, Payload, Segment } from "../core/contract";
import { FieldColors } from "../core/colors";
import { layoutSegments, type InlinePiece, type LayoutUnit, type LineKind } from "../core/layout";
import { getAt, listItemOf } from "../core/paths";
import { useSldb, type SchemaIndex } from "./context";
import type { EditorContext } from "./editors/registry";
import { ReadonlyField } from "./editors/ReadonlyField";
import { InlineMarkdown } from "./InlineMarkdown";
import { editKey, type WriteTarget } from "./useDocumentEditor";

export interface SurfaceEditing {
  commit(target: WriteTarget, path: string, value: unknown): void;
  pendingKey: string | null;
  error: { key: string; message: string } | null;
}

export interface DocumentSurfaceProps {
  segments: Segment[];
  /** Documento al que se escribe; `null` deja todo en solo lectura. */
  target: WriteTarget | null;
  model: string;
  /** Payload propio: habilita agregar y quitar ítems de listas. */
  payload?: Payload;
  colors: FieldColors;
  sourceDoc?: string | null;
  editing: SurfaceEditing;
  schema?: SchemaIndex;
  highlight?: string | null;
  onOpenDoc?(id: string): void;
}

export function DocumentSurface(props: DocumentSurfaceProps) {
  const units = layoutSegments(props.segments);
  const free = units.length === 1 && units[0]?.unit === "block" && !isComposition(units[0].segment);
  return <div className={`surface${free ? " surface--free" : ""}`}>{units.map((unit, i) => renderUnit(unit, i, props))}</div>;
}

function renderUnit(unit: LayoutUnit, key: number, props: DocumentSurfaceProps): ReactNode {
  switch (unit.unit) {
    case "frontmatter":
      return (
        <dl key={key} className="props">
          {unit.rows.map((row) => (
            <div key={row.key} className="props__row">
              <dt>{row.key}</dt>
              <dd>{renderPieces(row.pieces, "property", props)}</dd>
            </div>
          ))}
        </dl>
      );
    case "line":
      return <Line key={key} kind={unit.kind} pieces={unit.pieces} props={props} />;
    case "list":
      return <ListUnit key={key} unit={unit} props={props} />;
    case "block":
      return isComposition(unit.segment) ? (
        <CompositionBlock key={key} segment={unit.segment} props={props} />
      ) : (
        <FieldSlot key={key} segment={unit.segment} context="block" props={props} />
      );
    case "piece":
      return <Transclusion key={key} piece={unit.segment} props={props} />;
  }
}

function isComposition(segment: FieldSegment): boolean {
  return segment.composition != null || segment.children.some((c) => c.type === "composition");
}

function renderPieces(pieces: InlinePiece[], context: EditorContext, props: DocumentSurfaceProps): ReactNode {
  return pieces.map((piece, i) =>
    piece.kind === "text" ? (
      context === "code" ? piece.text : <InlineMarkdown key={i} text={piece.text} />
    ) : (
      <FieldSlot key={i} segment={piece.segment} context={context} props={props} />
    ),
  );
}

function Line({ kind, pieces, props }: { kind: LineKind; pieces: InlinePiece[]; props: DocumentSurfaceProps }) {
  switch (kind.type) {
    case "heading": {
      const Tag = `h${Math.min(kind.level, 6)}` as "h1";
      return <Tag className="surface__heading">{renderPieces(pieces, "inline", props)}</Tag>;
    }
    case "quote":
      return <blockquote>{renderPieces(pieces, "inline", props)}</blockquote>;
    case "fence":
      return <div className="surface__fence" aria-hidden />;
    case "code":
      return <pre className="surface__code">{renderPieces(pieces, "code", props)}</pre>;
    case "table":
      return <pre className="surface__table-line">{renderPieces(pieces, "inline", props)}</pre>;
    default:
      return <p>{renderPieces(pieces, "inline", props)}</p>;
  }
}

function ListUnit({ unit, props }: { unit: Extract<LayoutUnit, { unit: "list" }>; props: DocumentSurfaceProps }) {
  const Tag = unit.ordered ? "ol" : "ul";
  const list = unit.listPath && props.payload ? getAt(props.payload, unit.listPath) : undefined;
  const canEdit = Array.isArray(list) && props.target !== null;
  const items = unit.items.filter((item) => !item.every((p) => p.kind === "field" && isEmptyPlaceholder(p.segment)));
  return (
    <Tag className="surface__list">
      {items.map((item, i) => (
        <li key={i}>{renderPieces(item, "inline", props)}</li>
      ))}
      {canEdit && unit.listPath && <AddItem listPath={unit.listPath} list={list as unknown[]} props={props} />}
    </Tag>
  );
}

function isEmptyPlaceholder(segment: FieldSegment): boolean {
  return segment.start === segment.end && listItemOf(segment.path) === null;
}

function AddItem({ listPath, list, props }: { listPath: string; list: unknown[]; props: DocumentSurfaceProps }) {
  const [open, setOpen] = useState(false);
  if (!open || !props.target) {
    return (
      <li className="surface__add">
        <button type="button" className="add-btn" onClick={() => setOpen(true)}>
          + agregar
        </button>
      </li>
    );
  }
  const target = props.target;
  return (
    <li className="surface__add">
      <input
        autoFocus
        className="add-input"
        aria-label={`Nuevo ítem de ${listPath}`}
        placeholder="Escribe y presiona Enter"
        onBlur={() => setOpen(false)}
        onKeyDown={(event) => {
          const text = event.currentTarget.value.trim();
          if (event.key === "Escape") setOpen(false);
          if (event.key === "Enter" && text) {
            props.editing.commit(target, listPath, [...list, text]);
            setOpen(false);
          }
        }}
      />
    </li>
  );
}

function FieldSlot({ segment, context, props }: { segment: FieldSegment; context: EditorContext; props: DocumentSurfaceProps }) {
  const { editors } = useSldb();
  const colorKey = FieldColors.keyFor(segment.path, props.sourceDoc);
  const slot = props.colors.slotOf(colorKey);
  const schemaField = props.schema?.field(props.model, segment.path);
  const target = props.target;
  const key = target ? editKey(target, segment.path) : "";
  const pending = props.editing.pendingKey === key;
  const error = props.editing.error?.key === key ? props.editing.error.message : undefined;
  const Editor = target ? editors.resolve(segment, context, schemaField) : ReadonlyField;
  const Tag = context === "block" ? "div" : "span";
  const dimmed = props.highlight && props.highlight !== colorKey;
  const item = listItemOf(segment.path);
  const list = item && props.payload ? getAt(props.payload, item.list) : undefined;

  return (
    <Tag
      className={`field field--${context} f-${slot}${dimmed ? " is-dimmed" : ""}`}
      data-field={segment.path}
      data-marker={segment.marker}
    >
      <Editor
        segment={segment}
        value={segment.value !== undefined ? segment.value : segment.text}
        schema={schemaField}
        context={context}
        pending={pending}
        error={error}
        onCommit={(value) => target && props.editing.commit(target, segment.path, value)}
      />
      {item && Array.isArray(list) && target && (
        <button
          type="button"
          className="icon-btn field__remove"
          aria-label={`Quitar ${segment.path}`}
          onClick={() => props.editing.commit(target, item.list, list.filter((_, i) => i !== item.index))}
        >
          ×
        </button>
      )}
      {error && <span className="field-error" role="alert">{error}</span>}
    </Tag>
  );
}

function CompositionBlock({ segment, props }: { segment: FieldSegment; props: DocumentSurfaceProps }) {
  const pieces = segment.children.filter((c): c is CompositionPiece => c.type === "composition");
  return (
    <section className="composition" aria-label={`Composición ${segment.path}`}>
      {pieces.length === 0 && <p className="composition__empty">Esta composición no incluye nada todavía.</p>}
      {pieces.map((piece) => (
        <Transclusion key={`${piece.ref_index}-${piece.ref}`} piece={piece} props={props} />
      ))}
    </section>
  );
}

export function Transclusion({ piece, props }: { piece: CompositionPiece; props: DocumentSurfaceProps }) {
  const source = piece.source;
  const target = source.doc ? { doc: source.doc, model: source.model } : null;
  return (
    <article className="transclusion">
      <header className="transclusion__source">
        {source.doc && props.onOpenDoc ? (
          <button type="button" className="link-btn" onClick={() => props.onOpenDoc?.(source.doc as string)}>
            {source.doc}
          </button>
        ) : (
          <span>{source.doc ?? source.path}</span>
        )}
        <span className="transclusion__model">{source.model}</span>
      </header>
      <DocumentSurface
        {...props}
        segments={piece.children}
        target={target}
        model={source.model}
        sourceDoc={source.doc}
        payload={undefined}
      />
    </article>
  );
}
