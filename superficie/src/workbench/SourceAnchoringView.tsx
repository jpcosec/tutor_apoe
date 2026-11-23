import React, { useEffect, useMemo, useRef, useState } from "react";
import { Schema } from "prosemirror-model";
import { EditorState, Plugin } from "prosemirror-state";
import { Decoration, DecorationSet, EditorView } from "prosemirror-view";
import type { SldbClient } from "../core/client";
import type {
  Edge,
  FieldRankHit,
  GraphDocument,
  SimilarityResult,
  StoredDocument,
} from "../core/contract";
import {
  classifyHits,
  DUPLICATE_DEBOUNCE_MS,
  duplicateQuery,
  duplicateRankParams,
  lineLabel,
  scorePercent,
  selectionAt,
  suggestSymbol,
  type AnchorSelection,
} from "../core/anchors";
import { similarityNotice } from "../core/similarity";
import { computeCoverage } from "./anchoring-coverage";
import "./anchoring.css";

const sourceViewerSchema = new Schema({
  nodes: {
    doc: { content: "text*" },
    text: {},
  },
});

export interface AnchoredAtomInfo {
  id: string;
  title: string;
  text: string;
  quote: string;
  status: string;
  kind: string;
  startOffset: number;
  endOffset: number;
  changed: boolean;
}

export interface SourceAnchoringViewProps {
  client: SldbClient;
  documents: GraphDocument[];
  activeSourceId: string | null;
  onSelectSource: (sourceId: string) => void;
  onDocumentsMutated: () => void;
  onNavigateToDoc: (docId: string) => void;
}

/**
 * Offsets que el AtomDoc ya declara (`start_offset`/`end_offset`, o `start`/`end`), si son
 * enteros válidos dentro del texto de la fuente; si no, null y se cae a buscar la cita.
 */
export function storedOffsets(fields: Record<string, unknown>, textLength: number): { start: number; end: number } | null {
  const pick = (a: unknown, b: unknown) => (typeof a === "number" ? a : typeof b === "number" ? b : NaN);
  const start = pick(fields.start_offset, fields.start);
  const end = pick(fields.end_offset, fields.end);
  if (!Number.isInteger(start) || !Number.isInteger(end)) return null;
  if (start < 0 || end <= start || end > textLength) return null;
  return { start, end };
}

function docTitle(doc: GraphDocument): string {
  const t = doc.payload?.title ?? doc.payload?.name;
  return typeof t === "string" && t.trim() ? t : doc.id;
}

/** `FuenteDoc:acta` o `acta` → `acta`. */
export function bareId(ref: string): string {
  const i = ref.indexOf(":");
  return (i >= 0 ? ref.slice(i + 1) : ref).trim();
}

/** `endpoint` (`Model:name` o `name`) nombra al documento `id`. */
export function isEndpoint(endpoint: string, id: string): boolean {
  return endpoint === id || endpoint.endsWith(`:${id}`);
}

/**
 * Consumidores del átomo: aristas que llegan a él (InformeDoc, SpecNodeDoc… apuntan al átomo)
 * y aristas que salen de él, salvo las que vuelven a su FuenteDoc de origen.
 */
export function downstreamLinks(edges: Edge[], atomId: string, sourceId?: string | null): Edge[] {
  return edges.filter((e) => {
    if (isEndpoint(e.target, atomId)) return !isEndpoint(e.source, atomId);
    if (isEndpoint(e.source, atomId)) {
      if (sourceId && isEndpoint(e.target, bareId(sourceId))) return false;
      return !e.target.toLowerCase().startsWith("fuente");
    }
    return false;
  });
}

/** Modelos de átomo: `AtomDoc` (demo y deskops), `AtomicDocumentDoc`, `ProtoAtomDoc`… */
export function isAtomModel(modelName: string): boolean {
  return modelName.toLowerCase().includes("atom");
}

/** Modelos que el demo nombra como fuente (`FuenteDoc`, `ActaDoc`, `*SourceDoc`). */
export function isNamedSourceModel(modelName: string): boolean {
  const m = modelName.toLowerCase();
  return m.includes("fuente") || m.includes("acta") || m.includes("source");
}

/** Texto anclable de un documento: `body`, `text`, `texto`, `cuerpo` o `content` no vacíos. */
export function sourceTextOf(payload: Record<string, unknown> | undefined): string {
  const fields = payload ?? {};
  for (const key of ["body", "text", "texto", "cuerpo", "content"]) {
    const v = fields[key];
    if (typeof v === "string" && v.trim().length > 0) return v;
  }
  return "";
}

/**
 * Fuente anclable: un modelo nombrado como fuente (demo) o, en un store real sin FuenteDoc
 * (`ArchitectureNarrativeDoc`, `RequestDoc`, `PlanDoc`…), cualquier documento no-átomo con prosa.
 */
export function isAnchorableSource(doc: GraphDocument): boolean {
  if (isAtomModel(doc.model_name)) return false;
  return isNamedSourceModel(doc.model_name) || sourceTextOf(doc.payload).length > 0;
}

/** Referencia del átomo a su origen: `source` (demo), `fuente_ref` o `provenance` (AtomDoc de deskops). */
export function atomSourceRef(atom: GraphDocument): string {
  const fields = atom.payload ?? {};
  for (const key of ["source", "fuente_ref", "provenance"]) {
    const v = fields[key];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return "";
}

const normPath = (p: string) => p.split("#")[0]!.replace(/^\.?\//, "").trim();

/**
 * Un átomo pertenece a la fuente si su referencia la nombra por id (`FuenteDoc:acta`, `acta`)
 * o por ruta (`provenance: docs/architecture/x.md`); vacía no pertenece a ninguna.
 */
export function atomBelongsToSource(atom: GraphDocument, sourceId: string, sourcePath?: string | null): boolean {
  const ref = atomSourceRef(atom);
  if (!ref) return false;
  if (bareId(ref) === bareId(sourceId)) return true;
  return Boolean(sourcePath) && normPath(ref) === normPath(sourcePath!);
}

/** Fuentes ordenadas: primero las nombradas como fuente, luego las que más átomos citan. */
export function rankSources(documents: GraphDocument[]): GraphDocument[] {
  const atoms = documents.filter((d) => isAtomModel(d.model_name));
  const cited = (d: GraphDocument) => atoms.filter((a) => atomBelongsToSource(a, d.id, d.path)).length;
  return documents
    .filter(isAnchorableSource)
    .map((d, i) => ({ d, i, named: isNamedSourceModel(d.model_name) ? 1 : 0, n: cited(d) }))
    .sort((a, b) => b.named - a.named || b.n - a.n || a.i - b.i)
    .map((x) => x.d);
}

type RankState =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "ok"; duplicates: FieldRankHit[]; similar: FieldRankHit[] }
  | { phase: "notice"; text: string }
  | { phase: "error"; text: string };

interface Popover {
  selection: AnchorSelection;
  top: number;
  left: number;
}

export const SourceAnchoringView: React.FC<SourceAnchoringViewProps> = ({
  client,
  documents,
  activeSourceId,
  onSelectSource,
  onDocumentsMutated,
  onNavigateToDoc,
}) => {
  const [sourceDetail, setSourceDetail] = useState<StoredDocument | null>(null);
  const [popover, setPopover] = useState<Popover | null>(null);
  const [symbol, setSymbol] = useState("");
  const [kind, setKind] = useState("");
  const [rank, setRank] = useState<RankState>({ phase: "idle" });
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [activeAtomId, setActiveAtomId] = useState<string | null>(null);
  const [downstream, setDownstream] = useState<Edge[]>([]);

  const pmContainerRef = useRef<HTMLDivElement | null>(null);
  const sheetRef = useRef<HTMLDivElement | null>(null);

  const sourceDocs = useMemo(() => rankSources(documents), [documents]);

  const selectedSourceId = useMemo(() => {
    if (activeSourceId) {
      const clean = bareId(activeSourceId);
      const found = sourceDocs.find((d) => d.id === activeSourceId || d.id === clean);
      if (found) return found.id;
    }
    return sourceDocs[0]?.id ?? null;
  }, [activeSourceId, documents, sourceDocs]);

  const atomDocs = useMemo(
    () => documents.filter((d) => isAtomModel(d.model_name)),
    [documents],
  );

  useEffect(() => {
    setPopover(null);
    setActiveAtomId(null);
    if (!selectedSourceId) {
      setSourceDetail(null);
      return;
    }
    let cancelled = false;
    client
      .document(selectedSourceId)
      .then((detail: StoredDocument) => {
        if (!cancelled) setSourceDetail(detail);
      })
      .catch(() => {
        if (!cancelled) setSourceDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [client, selectedSourceId]);

  const sourceText = useMemo(() => sourceTextOf(sourceDetail?.payload), [sourceDetail]);
  const selectedSourcePath = useMemo(
    () => sourceDetail?.path ?? documents.find((d) => d.id === selectedSourceId)?.path ?? null,
    [sourceDetail, documents, selectedSourceId],
  );

  const anchoredAtoms: AnchoredAtomInfo[] = useMemo(() => {
    if (!selectedSourceId) return [];
    const list: AnchoredAtomInfo[] = [];
    for (const atom of atomDocs) {
      if (!atomBelongsToSource(atom, selectedSourceId, selectedSourcePath)) continue;
      const fields = atom.payload ?? {};
      const bodyText = String(fields.text ?? fields.body ?? fields.cuerpo ?? fields.texto ?? fields.answer ?? "").trim();
      const explicitQuote = String(fields.quote ?? fields.cita ?? "").trim();
      const quote = explicitQuote || (sourceText && bodyText && sourceText.includes(bodyText) ? bodyText : "");
      const stored = storedOffsets(fields, sourceText.length);
      const idx = stored ? stored.start : quote && sourceText ? sourceText.indexOf(quote) : -1;
      const end = stored ? stored.end : idx >= 0 ? idx + quote.length : -1;
      list.push({
        id: atom.id,
        title: docTitle(atom),
        text: bodyText,
        quote,
        status: String(fields.status ?? fields.estado ?? "").trim(),
        kind: String(fields.kind ?? "").trim(),
        startOffset: idx >= 0 ? idx : -1,
        endOffset: idx >= 0 ? end : -1,
        // Con offsets guardados, la fuente cambió si el tramo ya no coincide con la cita.
        changed: stored
          ? Boolean(quote && sourceText.slice(stored.start, stored.end) !== quote)
          : Boolean(quote && idx < 0 && sourceText.length > 0),
      });
    }
    return list.sort((a, b) => {
      if (a.startOffset < 0 && b.startOffset >= 0) return 1;
      if (b.startOffset < 0 && a.startOffset >= 0) return -1;
      return a.startOffset - b.startOffset;
    });
  }, [atomDocs, selectedSourceId, selectedSourcePath, sourceText]);

  const coverage = useMemo(
    () =>
      computeCoverage(
        anchoredAtoms.map((a) => ({ start: a.startOffset, end: a.endOffset })),
        sourceText.length,
      ),
    [anchoredAtoms, sourceText],
  );

  const kindOptions = useMemo(
    () => [...new Set(atomDocs.map((a) => String(a.payload?.kind ?? "").trim()).filter(Boolean))],
    [atomDocs],
  );

  const effectiveActiveId =
    activeAtomId && anchoredAtoms.some((a) => a.id === activeAtomId)
      ? activeAtomId
      : (anchoredAtoms.find((a) => a.startOffset >= 0) ?? anchoredAtoms[0])?.id ?? null;

  // Enlaces downstream del átomo activo, desde el grafo real.
  useEffect(() => {
    if (!effectiveActiveId) {
      setDownstream([]);
      return;
    }
    let cancelled = false;
    const nodeId = `AtomDoc:${effectiveActiveId}`;
    client
      .getEdges(nodeId)
      .then((edges) => {
        if (!cancelled) setDownstream(downstreamLinks(edges, effectiveActiveId, selectedSourceId));
      })
      .catch(() => {
        if (!cancelled) setDownstream([]);
      });
    return () => {
      cancelled = true;
    };
  }, [client, effectiveActiveId, selectedSourceId]);

  // Lector ProseMirror de solo lectura con decoraciones inline + widget por átomo anclado.
  useEffect(() => {
    const container = pmContainerRef.current;
    if (!container) return;

    const docNode = sourceViewerSchema.node(
      "doc",
      null,
      sourceText ? [sourceViewerSchema.text(sourceText)] : [],
    );

    const highlightPlugin = new Plugin({
      props: {
        decorations(state) {
          const decos: Decoration[] = [];
          for (const a of anchoredAtoms) {
            if (a.startOffset < 0 || a.endOffset <= a.startOffset) continue;
            // doc > text*: la posición de ProseMirror es el offset 0-based del body.
            const from = a.startOffset;
            const to = Math.min(state.doc.content.size, a.endOffset);
            if (to <= from) continue;
            decos.push(
              Decoration.inline(from, to, {
                class: "wb-pm-anchored-span",
                title: `Anclado en AtomDoc:${a.id}: ${a.title}`,
              }),
            );
            decos.push(
              Decoration.widget(
                to,
                () => {
                  const sup = document.createElement("sup");
                  sup.className = "wb-pm-anchor-sup";
                  sup.textContent = `[${a.id} · ${a.startOffset}:${a.endOffset}]`;
                  return sup;
                },
                { side: 1, key: `anchor-${a.id}` },
              ),
            );
          }
          return DecorationSet.create(state.doc, decos);
        },
      },
    });

    const view = new EditorView(container, {
      state: EditorState.create({ doc: docNode, plugins: [highlightPlugin] }),
      editable: () => false,
      dispatchTransaction(tr) {
        const next = view.state.apply(tr);
        view.updateState(next);
        if (!tr.selectionSet) return;
        const { from, to } = next.selection;
        const selection = to > from ? selectionAt(sourceText, from, to) : null;
        if (!selection || selection.quote.trim().length < 3) return;
        let top = 0;
        let left = 0;
        try {
          const c = view.coordsAtPos(to);
          const box = sheetRef.current?.getBoundingClientRect();
          if (box) {
            top = c.bottom - box.top + 8;
            left = Math.max(0, Math.min(c.left - box.left, box.width - 420));
          }
        } catch {
          /* jsdom no mide */
        }
        setPopover({ selection, top, left });
        setSymbol(suggestSymbol(selection.quote));
        setMessage(null);
      },
    });

    return () => view.destroy();
  }, [sourceText, anchoredAtoms]);

  // Corpus Rank con debounce: los tres estados de SimilarityResult se tratan por separado.
  const quote = popover?.selection.quote ?? "";
  useEffect(() => {
    const q = duplicateQuery(quote);
    if (!q) {
      setRank({ phase: "idle" });
      return;
    }
    let cancelled = false;
    setRank({ phase: "loading" });
    const timer = setTimeout(() => {
      client
        .rank(duplicateRankParams(q))
        .then((res: SimilarityResult<FieldRankHit>) => {
          if (cancelled) return;
          if (res.status !== "ok") {
            setRank({ phase: "notice", text: similarityNotice(res) ?? "Similitud no disponible." });
            return;
          }
          setRank({ phase: "ok", ...classifyHits(res.hits) });
        })
        .catch((err: unknown) => {
          if (!cancelled)
            setRank({
              phase: "error",
              text: `Similitud no disponible: ${err instanceof Error ? err.message : String(err)}.`,
            });
        });
    }, DUPLICATE_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [client, quote]);

  useEffect(() => {
    if (!popover) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPopover(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [popover]);

  const handleCreate = async () => {
    if (!selectedSourceId || !popover || !symbol.trim()) return;
    const sourceModel = sourceDetail?.model_name ?? "FuenteDoc";
    const { quote: q, start, end } = popover.selection;
    setCreating(true);
    setMessage(null);
    try {
      const payload: Record<string, unknown> = {
        title: symbol.trim(),
        source: `${sourceModel}:${selectedSourceId}`,
        quote: q.trim(),
        text: q.trim(),
        body: q.trim(),
      };
      if (kind) payload.kind = kind;
      const created = await client.createDocument("AtomDoc", symbol.trim(), payload);
      setMessage(`Creado ${created.id} y anclado en body[${start}:${end}]`);
      setPopover(null);
      onDocumentsMutated();
    } catch (err: unknown) {
      setMessage(`Error al crear AtomDoc: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setCreating(false);
    }
  };

  const sourceModel = sourceDetail?.model_name ?? "FuenteDoc";
  const sha = String(sourceDetail?.payload?.sha ?? sourceDetail?.payload?.hash ?? "");
  const sourceKind = String(
    sourceDetail?.payload?.kind ?? sourceDetail?.payload?.type ?? sourceDetail?.payload?.tipo ?? "",
  ).trim();

  const rankLine = (() => {
    switch (rank.phase) {
      case "idle":
        return "Corpus Rank: selecciona un pasaje de al menos 12 caracteres.";
      case "loading":
        return "Corpus Rank: buscando...";
      case "notice":
      case "error":
        return `Corpus Rank: ${rank.text}`;
      case "ok": {
        const best = rank.duplicates[0] ?? rank.similar[0];
        if (!best) return "✓ Corpus Rank (/corpus/rank?fields=1): Nuevo en el store";
        const label = rank.duplicates.length > 0 ? "Posible duplicado" : "Parecido";
        return `Corpus Rank (/corpus/rank?fields=1): ${label} ${scorePercent(best.score)}% con ${best.document_id || best.id}`;
      }
    }
  })();

  return (
    <div className="wb-split-38-62" data-testid="source-anchoring-view">
      <aside className="wb-pane-left-38 wb-anc-left">
        <div>
          <div className="wb-anc-head">
            <span className="wb-anc-kicker">TOPOLOGÍA DE EXTRACCIÓN Y ANCLAJE (SLDB AST)</span>
          </div>
          <select
            className="wb-input"
            aria-label="FuenteDoc"
            value={selectedSourceId ?? ""}
            onChange={(e) => onSelectSource(e.target.value)}
          >
            {sourceDocs.map((d) => (
              <option key={d.id} value={d.id}>
                {d.model_name}:{d.id} — {docTitle(d)}
              </option>
            ))}
          </select>

          {sourceDetail && (
            <div className="wb-anc-root" data-testid="anchoring-root">
              <div className="wb-anc-root-meta">
                <span>{sourceModel}</span>
                <span>id: {sourceDetail.id}</span>
              </div>
              <div className="wb-serif" style={{ fontSize: 13, fontWeight: 500 }}>
                {String(sourceDetail.payload?.title ?? sourceDetail.id)}
              </div>
              <div
                className="wb-anc-root-meta"
                style={{ marginTop: 4, paddingTop: 4, borderTop: "1px solid var(--wb-hairline)" }}
              >
                <span>field: body</span>
                {sha && <span>sha: {sha}</span>}
              </div>
            </div>
          )}

          <div className="wb-anc-branch">
            <div className="wb-anc-branch-label">&lt;- source (body[start:end])</div>
            {anchoredAtoms.length === 0 && (
              <div className="wb-mono" style={{ fontSize: 11, color: "var(--wb-ink-muted)" }}>
                Sin átomos anclados a esta fuente.
              </div>
            )}
            {anchoredAtoms.map((atom) => {
              const active = atom.id === effectiveActiveId;
              const proposed = atom.status === "propuesto";
              return (
                <div
                  key={atom.id}
                  role="button"
                  tabIndex={0}
                  data-testid={`anchor-atom-${atom.id}`}
                  className={`wb-anc-atom${active ? " wb-anc-atom--active" : ""}${proposed ? " wb-anc-atom--pending" : ""}`}
                  onClick={() => setActiveAtomId(atom.id)}
                  onDoubleClick={() => onNavigateToDoc(atom.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") setActiveAtomId(atom.id);
                  }}
                >
                  <div className="wb-anc-atom-row">
                    <span className="wb-mono" style={{ fontSize: 11, fontWeight: active ? 600 : 400 }}>
                      {atom.id}
                    </span>
                    <span style={{ display: "flex", gap: 4 }}>
                      <span className="wb-chip">
                        {atom.startOffset >= 0
                          ? `body[${atom.startOffset}:${atom.endOffset}]`
                          : atom.changed
                            ? "cita alterada"
                            : "sin cita"}
                      </span>
                      {atom.status && <span className="wb-chip wb-chip--wash">{atom.status}</span>}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 500 }}>{atom.title}</div>
                  {atom.quote && <div className="wb-anc-quote">“{atom.quote}”</div>}
                  {active && (
                    <div className="wb-anc-down">
                      <div className="wb-anc-kicker" style={{ fontSize: 9 }}>
                        DOWNSTREAM AST LINKS ({downstream.length}):
                      </div>
                      {downstream.map((e) => {
                        const inbound = isEndpoint(e.target, atom.id);
                        return (
                        <div key={e.id} className="wb-anc-link">
                          <span title={inbound ? "consumidor que apunta al átomo" : "arista saliente del átomo"}>
                            {inbound ? "←" : "→"}
                          </span>
                          <span style={{ fontWeight: 500 }}>{inbound ? e.source : e.target}</span>
                          <span style={{ marginLeft: "auto", color: "var(--wb-ink-muted)" }}>
                            ({e.type})
                          </span>
                        </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="wb-anc-cov" data-testid="anchoring-coverage">
          <div
            className="wb-anc-cov-row"
            style={{ fontWeight: 600, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}
          >
            <span>ESTADO DE COBERTURA DE EXTRACCIÓN</span>
            <span style={{ color: "var(--wb-ink-muted)" }}>SLDB/AST</span>
          </div>
          <div className="wb-anc-cov-row">
            <span style={{ color: "var(--wb-ink-muted)" }}>body coverage:</span>
            <span data-testid="coverage-pct">
              {coverage.pct}% anclado ({coverage.coveredChars}/{coverage.totalChars} caracteres,{" "}
              {anchoredAtoms.filter((a) => a.startOffset >= 0).length}/{anchoredAtoms.length} átomos
              mapeados)
            </span>
          </div>
          <div className="wb-anc-bar">
            <div style={{ width: `${coverage.pct}%` }} />
          </div>
        </div>
      </aside>

      <section className="wb-pane-right-62 wb-anc-right">
        <div className="wb-anc-sheet" ref={sheetRef}>
          {sourceDetail ? (
            <header style={{ paddingBottom: 24, borderBottom: "1px solid var(--wb-hairline)" }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                {sourceKind && <span className="wb-chip">{sourceKind}</span>}
                <span className="wb-mono" style={{ fontSize: 10, color: "var(--wb-ink-muted)" }}>
                  {sourceDetail.path}
                </span>
              </div>
              <h1 className="wb-anc-h1">{String(sourceDetail.payload?.title ?? sourceDetail.id)}</h1>
              <div className="wb-anc-meta">
                {sourceModel} · field: body · {sourceText.length} caracteres
                {sha ? ` · hash: ${sha}` : ""}
              </div>
            </header>
          ) : (
            <div className="wb-mono" style={{ color: "var(--wb-ink-muted)" }}>
              Cargando documento fuente...
            </div>
          )}

          <div className="wb-anc-reader">
            <div ref={pmContainerRef} data-testid="prosemirror-source-viewer" />
          </div>

          {message && (
            <div className="wb-mono" style={{ fontSize: 11, marginTop: 12 }} role="status">
              {message}
            </div>
          )}

          {popover && (
            <div
              className="wb-anc-popover"
              role="dialog"
              data-testid="anchor-popover"
              style={{ top: popover.top, left: popover.left }}
            >
              <div className="wb-anc-pop-head">
                Nuevo AtomDoc desde body[{popover.selection.start}:{popover.selection.end}] (
                {lineLabel(popover.selection)})
              </div>
              <div className="wb-anc-pop-grid">
                <div>
                  <label className="wb-anc-label" htmlFor="anc-symbol">
                    symbol / id:
                  </label>
                  <input
                    id="anc-symbol"
                    className="wb-input"
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value)}
                  />
                </div>
                <div>
                  <label className="wb-anc-label" htmlFor="anc-kind">
                    kind:
                  </label>
                  <select
                    id="anc-kind"
                    className="wb-input"
                    value={kind}
                    onChange={(e) => setKind(e.target.value)}
                  >
                    <option value="">(sin kind)</option>
                    {kindOptions.map((k) => (
                      <option key={k} value={k}>
                        {k}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="wb-anc-rank" data-testid="anchor-rank-status">
                {rankLine}
                {rank.phase === "ok" &&
                  [...rank.duplicates, ...rank.similar].map((h) => (
                    <div key={h.id}>
                      {scorePercent(h.score)}% {h.document_id || h.id}/{h.field}
                    </div>
                  ))}
              </div>
              <div className="wb-anc-pop-actions">
                <button
                  type="button"
                  className="wb-btn wb-btn--primary"
                  disabled={creating || !symbol.trim()}
                  onClick={handleCreate}
                >
                  [ Crear AtomDoc y Anclar ]
                </button>
                <button type="button" className="wb-btn" onClick={() => setPopover(null)}>
                  Cancelar
                </button>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
};
