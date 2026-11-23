/**
 * Compositor: arma un documento desde otros. Arrastrar reordena la composición,
 * "Quitar" saca la pieza del documento sin borrar su origen, y editar dentro de una
 * pieza escribe en el documento de origen.
 */
import { useMemo, useState } from "react";
import { DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { CompositionPiece, DocumentSegments, FieldSegment, GraphDocument } from "../core/contract";
import { getAt, insertAt, moveAt, removeAt } from "../core/paths";
import { useDocuments } from "../react/context";
import { Transclusion, type DocumentSurfaceProps } from "../react/DocumentSurface";

interface ComposerProps {
  data: DocumentSegments;
  surface: Omit<DocumentSurfaceProps, "segments">;
  commitList(path: string, next: (payload: DocumentSegments["payload"]) => DocumentSegments["payload"]): void;
}

export function ComposerView({ data, surface, commitList }: ComposerProps) {
  const compositions = data.segments.filter((s): s is FieldSegment => s.type === "field" && s.composition != null);
  if (compositions.length === 0) {
    return <p className="empty-state">Este documento no compone otros. La composición se declara en el modelo con <code>__compositions__</code>.</p>;
  }
  return (
    <div className="composer">
      {compositions.map((segment) => (
        <CompositionEditor key={segment.path} segment={segment} data={data} surface={surface} commitList={commitList} />
      ))}
    </div>
  );
}

function CompositionEditor({ segment, data, surface, commitList }: ComposerProps & { segment: FieldSegment }) {
  const spec = segment.composition!;
  const listPath = spec.source_field ?? "";
  const refs = (getAt(data.payload, listPath) as unknown[] | undefined) ?? [];
  const pieces = new Map(
    segment.children.filter((c): c is CompositionPiece => c.type === "composition").map((p) => [p.ref_index, p]),
  );
  const ids = refs.map((ref, i) => `${i}:${String(ref)}`);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    const from = ids.indexOf(String(active.id));
    const to = ids.indexOf(String(over.id));
    if (from >= 0 && to >= 0) commitList(listPath, (p) => moveAt(p, listPath, from, to));
  };

  return (
    <section className="composer__section" aria-label={`Composición ${spec.name}`}>
      <header className="composer__head">
        <h2>{spec.name}</h2>
        <p>
          {refs.length} {refs.length === 1 ? "pieza" : "piezas"} de <strong>{spec.model ?? "cualquier modelo"}</strong>, en el orden de <code>{listPath}</code>
        </p>
      </header>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          <ol className="composer__list">
            {ids.map((id, index) => (
              <SortablePiece key={id} id={id} piece={pieces.get(index)} rawRef={String(refs[index])} surface={surface} onRemove={() => commitList(listPath, (p) => removeAt(p, listPath, index))} />
            ))}
          </ol>
        </SortableContext>
      </DndContext>
      <AddPiece model={spec.model} included={refs.map(String)} onAdd={(doc) => commitList(listPath, (p) => insertAt(p, listPath, refs.length, doc.path))} />
    </section>
  );
}

function SortablePiece({ id, piece, rawRef, surface, onRemove }: { id: string; piece?: CompositionPiece; rawRef: string; surface: ComposerProps["surface"]; onRemove(): void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  const style = { transform: CSS.Transform.toString(transform), transition };
  return (
    <li ref={setNodeRef} style={style} className={`composer__item${isDragging ? " is-dragging" : ""}`}>
      <button type="button" className="drag-handle" aria-label="Arrastrar para reordenar" {...attributes} {...listeners}>
        ⠿
      </button>
      <div className="composer__body">
        {piece ? (
          <Transclusion piece={piece} props={{ ...surface, segments: piece.children }} />
        ) : (
          <p className="composer__broken">
            No se encontró <code>{rawRef}</code>. Quítala o corrige la ruta en la lista.
          </p>
        )}
      </div>
      <button type="button" className="btn btn--quiet" onClick={onRemove} title="Saca la pieza de este documento; el documento de origen no se borra">
        Quitar
      </button>
    </li>
  );
}

function AddPiece({ model, included, onAdd }: { model: string | null; included: string[]; onAdd(doc: GraphDocument): void }) {
  const [documents] = useDocuments();
  const [query, setQuery] = useState("");
  const candidates = useMemo(() => {
    if (documents.status !== "ready") return [];
    const q = query.trim().toLowerCase();
    return documents.data
      .filter((d) => (!model || d.model_name === model) && !included.includes(d.path))
      .filter((d) => !q || `${d.id} ${String(d.payload.title ?? "")}`.toLowerCase().includes(q))
      .slice(0, 12);
  }, [documents, included, model, query]);

  return (
    <div className="composer__add">
      <input type="search" className="add-input" placeholder={`Buscar ${model ?? "documento"} para agregar`} aria-label="Buscar pieza para agregar" value={query} onChange={(e) => setQuery(e.target.value)} />
      <ul>
        {candidates.map((doc) => (
          <li key={doc.id}>
            <button type="button" className="candidate" onClick={() => onAdd(doc)}>
              <span>{String(doc.payload.title ?? doc.id)}</span>
              <span className="candidate__id">{doc.id}</span>
            </button>
          </li>
        ))}
        {documents.status === "ready" && candidates.length === 0 && <li className="composer__none">No hay más documentos {model ? `de ${model}` : ""} para agregar.</li>}
      </ul>
    </div>
  );
}
