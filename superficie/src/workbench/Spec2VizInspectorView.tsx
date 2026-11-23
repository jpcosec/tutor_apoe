import React, { useCallback, useEffect, useMemo, useState } from "react";
import type { SldbClient } from "../core/client";
import type {
  Edge,
  GraphDocument,
  NotationLink,
  NotationNode,
  ResolvedNotationView,
} from "../core/contract";
import { NotationSvgCanvas, isAtomDocRef } from "./NotationSvgCanvas";
import "./spec2viz.css";

export interface Spec2VizInspectorViewProps {
  client: SldbClient;
  documents: GraphDocument[];
  activeSpecId: string | null;
  activeNodeDoc: string | null;
  onSelectSpec: (specId: string) => void;
  onSelectNode: (nodeDoc: string | null) => void;
  onNavigateToDoc: (docId: string) => void;
  onNavigateToSource: (sourceDocId: string) => void;
}

function docTitle(doc: GraphDocument): string {
  const t = doc.payload?.title ?? doc.payload?.name;
  return typeof t === "string" && t.trim() ? t : doc.id;
}

function splitRef(ref: string): { model: string | null; name: string } {
  const i = ref.indexOf(":");
  return i < 0 ? { model: null, name: ref } : { model: ref.slice(0, i), name: ref.slice(i + 1) };
}

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** `SpecNodeDoc:<id>` una sola vez: el store real ya trae el prefijo en `node.doc`. */
export function qualifiedNodeDoc(doc: string): string {
  return doc.includes(":") ? doc : `SpecNodeDoc:${doc}`;
}

export const Spec2VizInspectorView: React.FC<Spec2VizInspectorViewProps> = ({
  client,
  documents,
  activeSpecId,
  activeNodeDoc,
  onSelectSpec,
  onSelectNode,
  onNavigateToDoc,
  onNavigateToSource,
}) => {
  const [view, setView] = useState<ResolvedNotationView | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nodeEdges, setNodeEdges] = useState<Edge[]>([]);
  const [fetchedRefs, setFetchedRefs] = useState<Record<string, GraphDocument>>({});

  const specDocs = useMemo(
    () =>
      // `/notations/view` solo resuelve `SpecDoc:`; `DeskSpecDoc` y otros *Spec* no son diagramas.
      documents.filter((d) => d.model_name === "SpecDoc"),
    [documents],
  );

  const selectedSpecId = useMemo(() => {
    if (activeSpecId) {
      const clean = activeSpecId.includes(":") ? activeSpecId.split(":")[1]! : activeSpecId;
      const match = specDocs.find((d) => d.id === activeSpecId || d.id === clean);
      if (match) return match.id;
      return activeSpecId;
    }
    return specDocs[0]?.id ?? null;
  }, [activeSpecId, specDocs]);

  useEffect(() => {
    if (!selectedSpecId) {
      setView(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    client
      .notationView(selectedSpecId)
      .then((res: ResolvedNotationView) => {
        if (cancelled) return;
        setView(res);
        setLoading(false);
        if (!activeNodeDoc && res.nodes.length > 0) {
          onSelectNode(res.nodes[0]!.doc);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setView(null);
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client, selectedSpecId]);

  const selectedIndex = useMemo(() => {
    if (!view || view.nodes.length === 0) return -1;
    if (activeNodeDoc) {
      const i = view.nodes.findIndex((n) => n.doc === activeNodeDoc || n.element === activeNodeDoc);
      if (i >= 0) return i;
    }
    return 0;
  }, [view, activeNodeDoc]);
  const selectedNode: NotationNode | null = view && selectedIndex >= 0 ? view.nodes[selectedIndex]! : null;

  const docById = useMemo(() => {
    const m = new Map<string, GraphDocument>();
    for (const d of documents) m.set(d.id, d);
    for (const d of Object.values(fetchedRefs)) m.set(d.id, d);
    return m;
  }, [documents, fetchedRefs]);

  const selectedDocKey = selectedNode?.doc ?? null;
  useEffect(() => {
    if (!selectedNode) {
      setNodeEdges([]);
      return;
    }
    let cancelled = false;
    const nodeGid = selectedNode.doc.includes(":") ? selectedNode.doc : `SpecNodeDoc:${selectedNode.doc}`;
    client
      .getEdges(nodeGid)
      .then((edges: Edge[]) => {
        if (!cancelled) setNodeEdges(edges ?? []);
      })
      .catch(() => {
        if (!cancelled) setNodeEdges([]);
      });
    // Átomos que no vienen en `documents`: se resuelven desde el store.
    for (const ref of selectedNode.refs.filter(isAtomDocRef)) {
      const { name } = splitRef(ref);
      if (documents.some((d) => d.id === name)) continue;
      client
        .document(name)
        .then((detail) => {
          if (!cancelled) setFetchedRefs((prev) => ({ ...prev, [name]: detail as unknown as GraphDocument }));
        })
        .catch(() => {
          /* el átomo se muestra sin cita: no hay dato */
        });
    }
    return () => {
      cancelled = true;
    };
  }, [client, selectedDocKey]);

  const isAtomRef = useCallback(
    (ref: string) => isAtomDocRef(ref) || docById.get(splitRef(ref).name)?.model_name === "AtomDoc",
    [docById],
  );
  const { atomRefs, otherRefs } = useMemo(() => {
    const atoms: string[] = [];
    const others: string[] = [];
    for (const ref of selectedNode?.refs ?? []) (isAtomRef(ref) ? atoms : others).push(ref);
    return { atomRefs: atoms, otherRefs: others };
  }, [selectedNode, isAtomRef]);

  const matches = (id: string, node: NotationNode) => id === node.element || id === node.doc;
  const nodeLabel = (id: string): string => {
    const n = view?.nodes.find((x) => matches(id, x));
    return n ? qualifiedNodeDoc(n.doc) : id;
  };
  const inbound: NotationLink[] = selectedNode && view ? view.links.filter((l) => matches(l.target, selectedNode)) : [];
  const outbound: NotationLink[] = selectedNode && view ? view.links.filter((l) => matches(l.source, selectedNode)) : [];

  return (
    <div className="wb-split-48-52" data-testid="spec2viz-inspector-view">
      {/* Panel izquierdo: canvas Spec2Viz */}
      <section className="wb-pane-left-48">
        <div className="s2v-left-top">
          <h2 className="s2v-title">
            <span>
              ◇ SPEC2VIZ DIAGRAM CANVAS · NOTATION: {(view?.notation ?? "—").replace(/^NotationDoc:/, "")}
            </span>
          </h2>
          <div className="s2v-meta">
            {specDocs.length > 1 && (
              <select
                className="s2v-select"
                aria-label="Seleccionar SpecDoc"
                value={selectedSpecId ?? ""}
                onChange={(e) => onSelectSpec(e.target.value)}
                data-testid="spec-selector"
              >
                {specDocs.map((d) => (
                  <option key={d.id} value={d.id}>
                    {docTitle(d)}
                  </option>
                ))}
              </select>
            )}
            <span>zoom 100%</span>
            <span>|</span>
            <span>grid: dot</span>
          </div>
        </div>

        <div className="s2v-canvas">
          {loading && <div className="s2v-note">Proyectando vista de notación desde el store...</div>}
          {error && (
            <div className="s2v-note" role="alert">
              Error al resolver notación: {error}
            </div>
          )}
          {!loading && !error && !selectedSpecId && (
            <div className="s2v-note">No hay SpecDoc en el store.</div>
          )}
          {!loading && view && (
            <NotationSvgCanvas
              view={view}
              selectedNodeDoc={selectedNode?.doc ?? null}
              onSelectNode={(n) => onSelectNode(n.doc)}
              isAtomRef={isAtomRef}
            />
          )}
        </div>

        <footer className="s2v-footer">
          <div>
            {selectedNode ? (
              <>
                <span className="wb-chip">GlyphDoc: {selectedNode.glyph.replace(/^GlyphDoc:/, "")}</span>{" "}
                <span>
                  (where: kind = "{selectedNode.kind}" → shape: {selectedNode.shape})
                </span>
              </>
            ) : (
              <span>GlyphDoc: —</span>
            )}
          </div>
          <div>engine: spec2viz-renderer</div>
        </footer>
      </section>

      {/* Panel derecho: inspector del SpecNodeDoc */}
      <section className="wb-pane-right-52">
        <div className="s2v-sheet">
          {!selectedNode || !view ? (
            <div className="s2v-note">
              {error
                ? "Sin nodo: la notación no pudo resolverse."
                : "Selecciona un nodo en el diagrama para inspeccionar su SpecNodeDoc."}
            </div>
          ) : (
            <>
              <header className="s2v-head">
                <div className="s2v-head-top">
                  <span>{qualifiedNodeDoc(selectedNode.doc)}</span>
                  <span className="wb-chip wb-chip--wash">AST node #{selectedIndex + 1}</span>
                </div>
                <h1 className="s2v-h1">{(selectedNode.label || selectedNode.title).replace(/\n/g, " ")}</h1>
                <div className="s2v-sub">
                  SpecNodeDoc · kind: {selectedNode.kind} · spec: {view.spec}
                </div>
              </header>

              <div className="s2v-section">
                <div className="s2v-label">field: description</div>
                <p className="s2v-body">{str(selectedNode.data?.description) || selectedNode.title}</p>
              </div>

              <div className="s2v-section" data-testid="section-atom-refs">
                <div className="s2v-label">
                  atom_refs: [AtomDoc]
                  <small>{atomRefs.length} transclusiones</small>
                </div>
                <div className="s2v-stack">
                  {atomRefs.length === 0 && (
                    <div className="s2v-note">Este nodo no declara referencias a AtomDoc.</div>
                  )}
                  {atomRefs.map((ref) => {
                    const { name } = splitRef(ref);
                    const atom = docById.get(name);
                    const fields = atom?.payload ?? {};
                    const quoteField = str(fields.quote) ? "quote" : str(fields.text) ? "text" : null;
                    const quote = quoteField ? str(fields[quoteField]) : "";
                    const source = str(fields.source);
                    return (
                      <article key={ref} className="wb-transclusion-card" data-testid="atom-card">
                        <div className="wb-transclusion-card__header">
                          <span>
                            {atom?.path ?? name}
                            {quoteField ? ` → #${quoteField}` : ""} (AtomDoc · transcluded)
                          </span>
                          <span>
                            <button type="button" className="s2v-link" onClick={() => onNavigateToDoc(name)}>
                              ↗ {name}
                            </button>
                            {source && (
                              <>
                                {" · "}
                                <button
                                  type="button"
                                  className="s2v-link"
                                  onClick={() => onNavigateToSource(splitRef(source).name)}
                                >
                                  fuente: {source}
                                </button>
                              </>
                            )}
                          </span>
                        </div>
                        {quote ? (
                          <blockquote className="wb-transclusion-card__quote">“{quote}”</blockquote>
                        ) : (
                          <div className="s2v-note">AtomDoc sin cita ni texto en el store.</div>
                        )}
                      </article>
                    );
                  })}
                </div>
              </div>

              <div className="s2v-section" data-testid="section-refs">
                <div className="s2v-label">
                  refs: [Model:name]
                  <small>código &amp; rituales</small>
                </div>
                <div>
                  <h3 className="s2v-h3">Traced Code &amp; Tasks</h3>
                  {otherRefs.length === 0 ? (
                    <div className="s2v-note">Sin refs distintas de AtomDoc.</div>
                  ) : (
                    <ul className="s2v-list">
                      {otherRefs.map((ref) => {
                        const { model, name } = splitRef(ref);
                        const doc = docById.get(name);
                        return (
                          <li key={ref}>
                            <div>
                              <div>
                                <strong>{model ?? doc?.model_name ?? "?"}</strong>
                                <span className="wb-mono">: {name}</span>
                              </div>
                              {doc?.path && <div style={{ fontSize: 11, color: "var(--wb-ink-muted)" }}>{doc.path}</div>}
                            </div>
                            <button type="button" className="s2v-link" onClick={() => onNavigateToDoc(name)}>
                              ↗
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              </div>

              <div className="s2v-section" data-testid="section-edges">
                <div className="s2v-label">
                  edges: [RelationDoc]
                  <small>topología de flujo</small>
                </div>
                <div className="s2v-stack" style={{ gap: 8 }}>
                  {inbound.length === 0 && outbound.length === 0 && (
                    <div className="s2v-note">sin enlaces en view.links</div>
                  )}
                  {inbound.map((l, i) => (
                    <div key={`in-${i}`} className="s2v-edge s2v-edge--in" data-testid="edge-inbound">
                      <span>
                        <strong>← {l.relation}</strong> from <strong>{nodeLabel(l.source)}</strong>
                        {l.label && <span className="wb-chip"> label: "{l.label}"</span>}
                      </span>
                      <span className="s2v-edge-dir">&lt;- inbound</span>
                    </div>
                  ))}
                  {outbound.map((l, i) => (
                    <div key={`out-${i}`} className="s2v-edge" data-testid="edge-outbound">
                      <span>
                        <strong>→ {l.relation}</strong>
                        {l.label && <span className="wb-chip"> label: "{l.label}"</span>} to{" "}
                        <strong>{nodeLabel(l.target)}</strong>
                      </span>
                      <span className="s2v-edge-dir">-&gt; outbound</span>
                    </div>
                  ))}
                  {nodeEdges.length > 0 && (
                    <>
                      <h3 className="s2v-h3" style={{ marginTop: 12 }}>
                        Relaciones del grafo ({nodeEdges.length})
                      </h3>
                      {nodeEdges.map((e) => (
                        <div key={e.id} className="s2v-edge" data-testid="graph-edge">
                          <span>
                            {e.source} → {e.target}
                          </span>
                          <span className="s2v-edge-dir">
                            {e.type}
                            {e.relationDoc ? ` · ${e.relationDoc}` : ""}
                          </span>
                        </div>
                      ))}
                    </>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  );
};
