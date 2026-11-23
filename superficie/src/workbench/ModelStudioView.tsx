import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { EditorState as CmEditorState } from "@codemirror/state";
import { EditorView as CmEditorView } from "@codemirror/view";
import { markdown } from "@codemirror/lang-markdown";
import type { SldbClient } from "../core/client";
import type {
  AuthorityKind,
  GraphDocument,
  ModelCatalogEntry,
  ModelDescription,
  ModelValidationReport,
} from "../core/contract";
import { canEditModelContract } from "../core/authority";
import {
  AUTHORITY_OPTIONS,
  FIELD_GLYPH,
  FIELD_TYPE_OPTIONS,
  annotationTargetModel,
  deriveUmlNeighbours,
  fieldKind,
  isCleanReport,
  layoutUml,
  markersForField,
  promoteGate,
  reversibleBadge,
} from "./model-studio-logic";
import "./model-studio.css";

export interface ModelStudioViewProps {
  client: SldbClient;
  documents: GraphDocument[];
  activeModelName: string | null;
  onSelectModel: (modelName: string) => void;
  onModelsMutated: () => void;
}

const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e));

const FieldRows: React.FC<{ detail: ModelDescription; withBadge: boolean }> = ({ detail, withBadge }) => (
  <div className="ms-fields">
    {detail.fields.map((f) => {
      const kind = fieldKind(detail, f);
      const badge = withBadge ? reversibleBadge(detail.template, f.name) : null;
      return (
        <div key={f.name} className="ms-field-row">
          <span>
            <span className="ms-glyph">{FIELD_GLYPH[kind]}</span> {f.name}: <span className="ms-type">{f.annotation}</span>
          </span>
          {badge && <span className="ms-badge">{badge}</span>}
        </div>
      );
    })}
  </div>
);

export const ModelStudioView: React.FC<ModelStudioViewProps> = ({
  client,
  documents,
  activeModelName,
  onSelectModel,
  onModelsMutated,
}) => {
  const [catalog, setCatalog] = useState<ModelCatalogEntry[]>([]);
  const [detail, setDetail] = useState<ModelDescription | null>(null);
  const [neighbourDetails, setNeighbourDetails] = useState<Record<string, ModelDescription>>({});
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  // Bug #8: la validación vale solo para (modelo, revisión del draft) sobre los que corrió.
  const [draftRev, setDraftRev] = useState(0);
  const draftRevRef = useRef(0);
  const [validation, setValidation] = useState<{ model: string; rev: number; report: ModelValidationReport } | null>(null);

  const [newFieldName, setNewFieldName] = useState("");
  const [newFieldType, setNewFieldType] = useState<string>("str");
  const [newFieldDefault, setNewFieldDefault] = useState("");
  const [newFieldDesc, setNewFieldDesc] = useState("");

  const [templateDraft, setTemplateDraft] = useState("");
  const [backfillEnabled, setBackfillEnabled] = useState(true);

  const cmContainerRef = useRef<HTMLDivElement | null>(null);
  const cmViewRef = useRef<CmEditorView | null>(null);
  const detailReq = useRef(0);

  const loadCatalog = useCallback(() => {
    client
      .modelsCatalog()
      .then((res) => setCatalog(res ?? []))
      .catch(() => {
        /* el catálogo es opcional para el resto de la vista */
      });
  }, [client]);

  useEffect(() => {
    loadCatalog();
  }, [loadCatalog]);

  const selectedModel = useMemo(() => {
    if (activeModelName && catalog.some((m) => m.name === activeModelName)) return activeModelName;
    return catalog[0]?.name ?? activeModelName ?? null;
  }, [activeModelName, catalog]);

  const bumpDraft = useCallback(() => {
    draftRevRef.current += 1;
    setDraftRev(draftRevRef.current);
    setValidation(null);
  }, []);

  const loadModelDetail = useCallback(
    (modelName: string) => {
      const req = ++detailReq.current;
      setLoading(true);
      client
        .describeModel(modelName)
        .then((res) => {
          if (req !== detailReq.current) return;
          setDetail(res);
          setTemplateDraft(res.template ?? "");
          setLoading(false);
        })
        .catch((err: unknown) => {
          if (req !== detailReq.current) return;
          setStatusMessage(`Error al cargar modelo: ${errMsg(err)}`);
          setLoading(false);
        });
    },
    [client],
  );

  // Cambio de modelo: invalida la validación y recarga el contrato.
  useEffect(() => {
    if (!selectedModel) return;
    bumpDraft();
    setStatusMessage(null);
    loadModelDetail(selectedModel);
  }, [selectedModel, loadModelDetail, bumpDraft]);

  const shown = detail && detail.name === selectedModel ? detail : null;

  const editPermission = useMemo(() => {
    if (!shown) return { editable: false, owner: "local" as string, reason: "" as string | undefined };
    return canEditModelContract(shown);
  }, [shown]);

  // Vecinos UML: se describen vía cliente para mostrar sus campos.
  const neighbours = useMemo(
    () => (shown ? deriveUmlNeighbours(shown, catalog, documents) : []),
    [shown, catalog, documents],
  );
  const neighbourKey = neighbours.map((n) => n.model).join("|");
  useEffect(() => {
    let cancelled = false;
    for (const n of neighbours) {
      client
        .describeModel(n.model)
        .then((d) => {
          if (!cancelled) setNeighbourDetails((prev) => ({ ...prev, [n.model]: d }));
        })
        .catch(() => {
          /* el vecino se dibuja sin compartimento de campos */
        });
    }
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, neighbourKey]);

  // CodeMirror 6 para __template__.
  useEffect(() => {
    const container = cmContainerRef.current;
    if (!container || !shown) return;
    const view = new CmEditorView({
      state: CmEditorState.create({
        doc: shown.template ?? "",
        extensions: [
          markdown(),
          CmEditorView.editable.of(editPermission.editable),
          CmEditorView.updateListener.of((update) => {
            if (update.docChanged) setTemplateDraft(update.state.doc.toString());
          }),
        ],
      }),
      parent: container,
    });
    cmViewRef.current = view;
    return () => {
      view.destroy();
      cmViewRef.current = null;
    };
  }, [shown, editPermission.editable]);

  const afterMutation = (model: string) => {
    bumpDraft();
    loadModelDetail(model);
    loadCatalog();
  };

  const handleAuthorityChange = async (next: AuthorityKind) => {
    if (!shown || !editPermission.editable) return;
    setStatusMessage("Actualizando __authority__ en borrador...");
    try {
      await client.editModelMetadata(shown.name, { authority: next });
      setStatusMessage(`✓ Borrador actualizado: __authority__ = "${next}"`);
    } catch (err) {
      setStatusMessage(`Error: ${errMsg(err)}`);
    }
    afterMutation(shown.name);
  };

  const handleAddField = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!shown || !editPermission.editable || !newFieldName.trim()) return;
    const name = newFieldName.trim();
    setStatusMessage(`Añadiendo campo ${name}...`);
    try {
      await client.addModelField(shown.name, name, newFieldType, newFieldDesc.trim(), newFieldDefault.trim() || undefined);
      setNewFieldName("");
      setNewFieldDefault("");
      setNewFieldDesc("");
      setStatusMessage(`✓ Campo '${name}' añadido al draft de ${shown.name}`);
    } catch (err) {
      setStatusMessage(`Error: ${errMsg(err)}`);
    }
    afterMutation(shown.name);
  };

  const handleRemoveField = async (fieldName: string) => {
    if (!shown || !editPermission.editable) return;
    setStatusMessage(`Eliminando campo ${fieldName}...`);
    try {
      await client.removeModelField(shown.name, fieldName);
      setStatusMessage(`✓ Campo '${fieldName}' eliminado del draft`);
    } catch (err) {
      setStatusMessage(`Error: ${errMsg(err)}`);
    }
    afterMutation(shown.name);
  };

  const handleSaveTemplate = async () => {
    if (!shown || !editPermission.editable) return;
    setStatusMessage("Guardando __template__ en borrador...");
    try {
      await client.editModelTemplate(shown.name, templateDraft);
      setStatusMessage("✓ Plantilla __template__ actualizada en borrador");
    } catch (err) {
      setStatusMessage(`Error: ${errMsg(err)}`);
    }
    afterMutation(shown.name);
  };

  const handleValidate = async () => {
    if (!shown) return;
    const model = shown.name;
    const rev = draftRevRef.current;
    setStatusMessage("Validando contrato del draft contra las instancias del store...");
    try {
      const report = await client.validateModelDraft(model);
      // Si el draft cambió mientras validaba, el resultado ya no aplica.
      if (rev !== draftRevRef.current) return;
      setValidation({ model, rev, report });
      setStatusMessage(
        isCleanReport(report)
          ? `✓ Contrato válido (${report.affected_documents ?? 0} documentos afectados)`
          : "⚠ Contrato con errores de validación",
      );
    } catch (err) {
      setStatusMessage(`Error al validar: ${errMsg(err)}`);
    }
  };

  const gate = promoteGate({
    editable: editPermission.editable,
    readOnlyReason: editPermission.reason,
    hasDraft: Boolean(shown?.has_draft),
    templateDirty: Boolean(shown) && templateDraft !== (shown?.template ?? ""),
    validation,
    model: shown?.name ?? null,
    rev: draftRev,
  });

  const handlePromote = async () => {
    if (!shown || !gate.enabled) return;
    setStatusMessage("Promoviendo borrador a models.py y ejecutando backfill...");
    try {
      await client.promoteModelDraft(shown.name, backfillEnabled);
      setStatusMessage(`✓ Modelo ${shown.name} promovido a models.py`);
      afterMutation(shown.name);
      onModelsMutated();
    } catch (err) {
      setStatusMessage(`Error al promover: ${errMsg(err)}`);
    }
  };

  const instanceCount = useMemo(
    () => (selectedModel ? documents.filter((d) => d.model_name === selectedModel).length : 0),
    [documents, selectedModel],
  );

  const report = validation && validation.model === shown?.name && validation.rev === draftRev ? validation.report : null;
  const readOnlyHint = editPermission.editable ? undefined : editPermission.reason;

  // ---- Diagrama UML ----
  const layout = useMemo(() => {
    if (!shown) return null;
    const info: Record<string, { fields: number; hasBase: boolean }> = {};
    for (const n of neighbours) {
      const d = neighbourDetails[n.model];
      info[n.model] = { fields: d?.fields.length ?? 0, hasBase: (d?.base_models.length ?? 0) > 0 };
    }
    return layoutUml(shown.name, { fields: shown.fields.length, hasBase: shown.base_models.length > 0 }, neighbours, info);
  }, [shown, neighbours, neighbourDetails]);

  return (
    <div className="ms-root" data-testid="model-studio-view">
      <div className="wb-split-38-62">
        <section className="wb-pane-left-38" aria-label="Graph de clases">
          <div className="ms-pane-head">
            <span className="ms-pane-title">Graph de Clases &amp; Notación (SLDB)</span>
            <span className="ms-pane-meta">zoom: 100% · layout: strict-uml</span>
          </div>
          <div className="ms-canvas wb-paper-grid">
            {shown && layout && (
              <div className="ms-diagram" data-testid="uml-diagram" style={{ width: layout.width, height: layout.height }}>
                <svg className="ms-svg" width={layout.width} height={layout.height} aria-hidden="true">
                  <defs>
                    <marker id="ms-diamond" markerWidth="10" markerHeight="8" refX="0" refY="4" orient="auto">
                      <polygon points="0,4 5,1 10,4 5,7" fill="#1A1A1A" stroke="#1A1A1A" strokeWidth="0.8" />
                    </marker>
                    <marker id="ms-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                      <path d="M 0 1 L 7 4 L 0 7" fill="none" stroke="#73726E" strokeWidth="1.1" />
                    </marker>
                    <marker id="ms-ref-circle" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
                      <circle cx="3" cy="3" r="2" fill="#FAF9F6" stroke="#73726E" strokeWidth="1" />
                    </marker>
                  </defs>
                  {layout.connectors.map((c) => (
                    <path
                      key={`${c.to}`}
                      data-testid={`uml-connector-${c.kind}-${c.to}`}
                      d={c.path}
                      fill="none"
                      stroke={c.kind === "composition" ? "#1A1A1A" : "#73726E"}
                      strokeWidth={c.kind === "composition" ? 1.2 : 1}
                      strokeDasharray={c.kind === "reference" ? "3 3" : undefined}
                      markerStart={c.kind === "composition" ? "url(#ms-diamond)" : "url(#ms-ref-circle)"}
                      markerEnd="url(#ms-arrow)"
                    />
                  ))}
                </svg>
                {layout.boxes.map((b) => {
                  const d = b.root ? shown : neighbourDetails[b.model];
                  const entry = catalog.find((m) => m.name === b.model);
                  const base = d?.base_models.join(", ");
                  const stereo = b.root ? "«active root»" : entry?.family ? `«${entry.family}»` : "";
                  return (
                    <div
                      key={b.model}
                      role={b.root ? undefined : "button"}
                      data-testid={`uml-box-${b.model}`}
                      className={`ms-box ${b.root ? "ms-box--root" : ""}`}
                      style={{ left: b.x, top: b.y, width: b.w, height: b.h }}
                      onClick={b.root ? undefined : () => onSelectModel(b.model)}
                    >
                      <div className="ms-box-head">
                        <span>class {b.model}</span>
                        <span className="ms-stereo">{stereo}</span>
                      </div>
                      {base && <div className="ms-extends">extends {base}</div>}
                      {d && <FieldRows detail={d} withBadge />}
                    </div>
                  );
                })}
              </div>
            )}
            {!shown && !loading && <div className="ms-muted wb-mono">Sin modelo seleccionado.</div>}
          </div>
          <div className="ms-left-foot">
            <button
              type="button"
              className="wb-btn"
              disabled
              title="La operación create_model es del CLI (`sldb models create`) y `sldb serve` no la expone todavía."
            >
              [ + Nuevo Modelo (create_model) ]
            </button>
            <span>{catalog.length} registered classes</span>
          </div>
        </section>

        <section className="wb-pane-right-62" aria-label="Contrato de modelo">
          <div className="ms-right">
            {loading && !shown && <div className="ms-muted wb-mono">Cargando contrato...</div>}
            {shown && (
              <>
                <header className="ms-contract-head">
                  <div className="ms-head-row">
                    <h1 className="ms-title">
                      Contrato de Modelo: <code>{shown.name}</code>
                    </h1>
                    <label className="wb-mono" style={{ fontSize: 10, display: "flex", gap: 6, alignItems: "center" }}>
                      __authority__
                      <select
                        className="wb-input"
                        style={{ width: 130 }}
                        aria-label="__authority__"
                        disabled={!editPermission.editable}
                        title={readOnlyHint}
                        value={shown.authority}
                        onChange={(e) => handleAuthorityChange(e.target.value as AuthorityKind)}
                      >
                        {AUTHORITY_OPTIONS.map((a) => (
                          <option key={a} value={a}>
                            {a}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <p className="ms-subtitle">
                    extends {shown.base_models.length ? shown.base_models.join(", ") : "—"} · source: {shown.path || shown.model_ref || "—"} · v{shown.version}
                    {shown.has_draft && <span className="wb-chip wb-chip--wash" style={{ marginLeft: 8 }}>draft activo</span>}
                  </p>
                </header>

                {!editPermission.editable && (
                  <div className="ms-notice" data-testid="readonly-notice">
                    🔒 Contrato gobernado por {editPermission.owner}: {editPermission.reason}
                  </div>
                )}

                <section className="ms-section">
                  <div className="ms-section-head">
                    <span className="ms-section-title">
                      <span>01 /</span>Declaración de Campos &amp; Slots
                    </span>
                    <span className="ms-section-meta">{shown.fields.length} slots tipados</span>
                  </div>
                  <div className="ms-table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Campo</th>
                          <th>Tipo / Ref</th>
                          <th>Reversible Marker (⸢...⸥)</th>
                          <th>Comportamiento</th>
                          <th>Descripción Semántica</th>
                          <th style={{ width: 70 }} />
                        </tr>
                      </thead>
                      <tbody>
                        {shown.fields.map((f) => {
                          const kind = fieldKind(shown, f);
                          const target = annotationTargetModel(f.annotation);
                          const markers = markersForField(shown.template, f.name);
                          return (
                            <tr key={f.name}>
                              <td style={{ fontWeight: 600 }}>{f.name}</td>
                              <td className={kind === "plain" ? "ms-muted" : undefined}>{f.annotation}</td>
                              <td>
                                {markers.length ? (
                                  markers.map((m, i) => (
                                    <span key={i} className="ms-marker" style={{ marginRight: 4 }}>
                                      {m.raw}
                                    </span>
                                  ))
                                ) : (
                                  <span className="ms-muted">—</span>
                                )}
                              </td>
                              <td className="ms-muted" style={{ fontSize: 10.5 }}>
                                {kind === "composition"
                                  ? `composición${target ? ` → ${target}` : ""}`
                                  : kind === "reference"
                                    ? `referencia${target ? ` → ${target}` : ""}`
                                    : "—"}
                              </td>
                              <td className="ms-desc">{f.description || "—"}</td>
                              <td>
                                {editPermission.editable && f.name !== "title" && f.name !== "body" && (
                                  <button type="button" className="wb-btn" style={{ fontSize: 10 }} onClick={() => handleRemoveField(f.name)}>
                                    Quitar
                                  </button>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  <form className="ms-add" onSubmit={handleAddField} aria-label="Agregar campo">
                    <input
                      className="wb-input"
                      placeholder="nombre_campo"
                      aria-label="nombre del campo"
                      disabled={!editPermission.editable}
                      title={readOnlyHint}
                      value={newFieldName}
                      onChange={(e) => setNewFieldName(e.target.value)}
                    />
                    <select
                      className="wb-input"
                      aria-label="tipo del campo"
                      disabled={!editPermission.editable}
                      title={readOnlyHint}
                      value={newFieldType}
                      onChange={(e) => setNewFieldType(e.target.value)}
                    >
                      {FIELD_TYPE_OPTIONS.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                    <input
                      className="wb-input"
                      placeholder="descripción semántica"
                      aria-label="descripción del campo"
                      disabled={!editPermission.editable}
                      value={newFieldDesc}
                      onChange={(e) => setNewFieldDesc(e.target.value)}
                    />
                    <input
                      className="wb-input"
                      placeholder='default (ej. "")'
                      aria-label="default del campo"
                      disabled={!editPermission.editable}
                      value={newFieldDefault}
                      onChange={(e) => setNewFieldDefault(e.target.value)}
                    />
                    <button
                      type="submit"
                      className="wb-btn wb-btn--primary"
                      disabled={!editPermission.editable || !newFieldName.trim()}
                      title={readOnlyHint}
                    >
                      + Agregar campo
                    </button>
                  </form>
                </section>

                <section className="ms-section">
                  <div className="ms-section-head">
                    <span className="ms-section-title">
                      <span>02 /</span>Plantilla Reversible (Round-Trip MD Engines)
                    </span>
                    <button
                      type="button"
                      className="wb-btn"
                      disabled={!editPermission.editable}
                      title={readOnlyHint}
                      onClick={handleSaveTemplate}
                    >
                      Guardar plantilla
                    </button>
                  </div>
                  <div ref={cmContainerRef} className="ms-editor" data-testid="codemirror-template-editor" />
                </section>

                <section className="ms-section">
                  <div className="ms-section-head">
                    <span className="ms-section-title">
                      <span>03 /</span>Estado de Validación &amp; Migración
                    </span>
                    <span className="ms-section-meta">{instanceCount} documentos en el store</span>
                  </div>
                  <div className="ms-card" data-testid="validation-card">
                    {!report && <div className="ms-muted">Draft sin validar. Ejecuta “Validar Draft” para ver el reporte round-trip.</div>}
                    {report && (
                      <>
                        <div style={{ fontWeight: 600 }} data-testid="validation-verdict">
                          {isCleanReport(report)
                            ? `✓ Round-trip sin errores (${report.affected_documents ?? 0} documentos afectados)`
                            : "✗ Round-trip con errores"}
                        </div>
                        {(report.errors ?? []).length > 0 && (
                          <ul data-testid="validation-errors">
                            {(report.errors ?? []).map((e, i) => (
                              <li key={i}>error: {e}</li>
                            ))}
                          </ul>
                        )}
                        {(report.warnings ?? []).length > 0 && (
                          <ul data-testid="validation-warnings">
                            {(report.warnings ?? []).map((w, i) => (
                              <li key={i} className="ms-muted">
                                aviso: {w}
                              </li>
                            ))}
                          </ul>
                        )}
                        <div className="ms-metrics">
                          <span>
                            backfill_required:{" "}
                            <b>{(report.backfill_required ?? []).length ? (report.backfill_required ?? []).join(", ") : "ninguno"}</b>
                          </span>
                          <span>
                            affected_documents: <b>{report.affected_documents ?? 0}</b>
                          </span>
                        </div>
                      </>
                    )}
                    <div className="ms-actions">
                      <button type="button" className="wb-btn" onClick={handleValidate}>
                        Validar Draft
                      </button>
                      <label className="ms-muted" style={{ display: "flex", gap: 6, alignItems: "center" }}>
                        <input
                          type="checkbox"
                          checked={backfillEnabled}
                          disabled={!editPermission.editable}
                          onChange={(e) => setBackfillEnabled(e.target.checked)}
                        />
                        Backfill automático
                      </label>
                      <button
                        type="button"
                        className="wb-btn wb-btn--primary"
                        disabled={!gate.enabled}
                        title={gate.reason}
                        onClick={handlePromote}
                      >
                        Promover
                      </button>
                      <span className="ms-muted" data-testid="promote-reason">
                        {gate.reason}
                      </span>
                    </div>
                  </div>
                  {statusMessage && <div className="ms-status">{statusMessage}</div>}
                </section>
              </>
            )}
          </div>
        </section>
      </div>
      <footer className="wb-bottom-rail">
        <span>{shown ? `schema: ${shown.path}#${shown.name} · v${shown.version}` : "schema: —"}</span>
        <span>{shown?.has_draft ? `draft: ${shown.draft_path ?? ".models_draft.py"}` : "sin draft pendiente"}</span>
      </footer>
    </div>
  );
};
