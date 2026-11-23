/** Documento: render editable (Documento) o armado de composiciones (Composición). */
import { useMemo, useState } from "react";
import { FieldColors } from "../core/colors";
import { fieldRoots } from "../core/layout";
import { useSchema } from "../react/context";
import { DocumentSurface, type SurfaceEditing } from "../react/DocumentSurface";
import { Legend } from "../react/Legend";
import { useDocumentEditor } from "../react/useDocumentEditor";
import { ComposerView } from "./ComposerView";
import { hrefFor, navigate } from "./router";
import { ConflictBanner, SaveStatus } from "./SaveStatus";

export function DocumentView({ id, mode }: { id: string; mode: "document" | "compose" }) {
  const { data, loadError, save, reload, commit, commitPayload, dismiss } = useDocumentEditor(id);
  const schema = useSchema();
  const [highlight, setHighlight] = useState<string | null>(null);
  const colors = useMemo(() => new FieldColors(data ? fieldRoots(data.segments) : []), [data]);

  if (loadError) return <p className="empty-state">No se pudo abrir {id}: {loadError}</p>;
  if (!data) return <p className="empty-state">Abriendo {id}…</p>;

  const schemaIndex = schema.status === "ready" ? schema.data : undefined;
  const target = { doc: data.id, model: data.model };
  const editing: SurfaceEditing = {
    commit: (t, path, value) => void commit(t, path, value),
    pendingKey: save.status === "saving" ? save.key : null,
    error: save.status === "error" ? { key: save.key, message: save.message } : null,
  };
  const surface = {
    target,
    model: data.model,
    payload: data.payload,
    colors,
    editing,
    schema: schemaIndex,
    highlight,
    onOpenDoc: (doc: string) => navigate({ view: "doc", id: doc, mode: "document" }),
  };
  const composes = data.segments.some((s) => s.type === "field" && s.composition);
  const modelFields = schemaIndex?.models.find((m) => m.id === data.model)?.fields ?? [];
  const title = typeof data.payload.title === "string" ? data.payload.title : data.id;

  return (
    <div className="doc-view">
      <header className="doc-header">
        <div className="doc-header__id">
          <span className="doc-header__model">{data.model}</span>
          <span className="doc-header__path">{data.path}</span>
        </div>
        <nav className="tabs" aria-label="Modo">
          <a className={mode === "document" ? "is-active" : undefined} href={hrefFor({ view: "doc", id, mode: "document" })}>
            Documento
          </a>
          {composes && (
            <a className={mode === "compose" ? "is-active" : undefined} href={hrefFor({ view: "doc", id, mode: "compose" })}>
              Composición
            </a>
          )}
        </nav>
        <SaveStatus save={save} />
      </header>
      <div className="doc-body">
        <main className="page" aria-label={title}>
          <ConflictBanner save={save} onReload={() => void reload().then(dismiss)} onDismiss={dismiss} />
          {data.canonical === false && (
            <div className="banner">El archivo en disco quedó distinto del render actual (por ejemplo, cambió un documento que este compone). El próximo guardado lo reescribe.</div>
          )}
          {mode === "compose" ? (
            <ComposerView data={data} surface={surface} commitList={(path, next) => void commitPayload(path, next)} />
          ) : (
            <DocumentSurface segments={data.segments} {...surface} />
          )}
        </main>
        <aside className="inspector">
          <Legend
            segments={data.segments}
            colors={colors}
            fields={modelFields}
            onHighlight={setHighlight}
            onAdd={(field, value) => void commit(target, field.name, value)}
          />
          {schema.status === "ready" && schema.data.errors.length > 0 && (
            <p className="inspector__note">{schema.data.errors.length} modelos del store no se pudieron importar.</p>
          )}
        </aside>
      </div>
    </div>
  );
}
