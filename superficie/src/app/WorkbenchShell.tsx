import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createHttpClient, type SldbClient } from "../core/client";
import type { GraphDocument, ModelCatalogEntry } from "../core/contract";
import type { AssistantClient } from "../core/assistant";
import { businessName } from "../core/wiki-index";
import { WorkbenchAssist } from "./WorkbenchAssist";
import { SldbProvider } from "../react/context";
import { ProsaWorkbenchView, type WorkbenchLens } from "../workbench/ProsaWorkbenchView";
import { Spec2VizInspectorView } from "../workbench/Spec2VizInspectorView";
import { SourceAnchoringView, isNamedSourceModel, rankSources } from "../workbench/SourceAnchoringView";
import { ModelStudioView } from "../workbench/ModelStudioView";
import {
  formatWorkbenchHash,
  parseWorkbenchHash,
  type WorkbenchRouteState,
  type WorkbenchViewId,
} from "./workbench-router";

export interface WorkbenchShellProps {
  baseUrl?: string;
  client?: SldbClient;
  /** Cliente del asistente; por defecto el puente local `/assistant`. */
  assistantClient?: AssistantClient;
}

/** Vista a la que lleva una lente de prosa: conserva diagram/source; desde studio vuelve al workbench. */
export function lensTargetView(current: WorkbenchViewId): WorkbenchViewId {
  return current === "studio" ? "workbench" : current;
}

function docTitle(doc: GraphDocument): string {
  const t = doc.payload?.title ?? doc.payload?.name;
  return typeof t === "string" && t.trim() ? t : doc.id;
}

export const WorkbenchShell: React.FC<WorkbenchShellProps> = ({
  baseUrl = "/sldb",
  client: injectedClient,
  assistantClient,
}) => {
  const client = useMemo(
    () => injectedClient ?? createHttpClient(baseUrl),
    [injectedClient, baseUrl],
  );

  const [route, setRoute] = useState<WorkbenchRouteState>(() =>
    parseWorkbenchHash(typeof window !== "undefined" ? window.location.hash : ""),
  );
  const [documents, setDocuments] = useState<GraphDocument[]>([]);
  const [models, setModels] = useState<ModelCatalogEntry[]>([]);
  const [paletteOpen, setPaletteOpen] = useState(false);
  // Sube cuando el asistente escribe en el store: las vistas se vuelven a montar y releen.
  const [viewEpoch, setViewEpoch] = useState(0);
  const [paletteQuery, setPaletteQuery] = useState("");
  const [storeStatus, setStoreStatus] = useState<
    { kind: "loading" } | { kind: "synced" } | { kind: "error"; message: string }
  >({ kind: "loading" });

  const navigate = useCallback(
    (next: Partial<WorkbenchRouteState> & { view: WorkbenchViewId }) => {
      const merged: WorkbenchRouteState = {
        view: next.view,
        doc: next.doc !== undefined ? next.doc : route.doc,
        lens: next.lens !== undefined ? next.lens : route.lens,
        spec: next.spec !== undefined ? next.spec : route.spec,
        node: next.node !== undefined ? next.node : route.node,
        model: next.model !== undefined ? next.model : route.model,
      };
      setRoute(merged);
      if (typeof window !== "undefined") {
        const nextHash = formatWorkbenchHash(merged);
        if (window.location.hash !== nextHash) {
          window.history.replaceState(null, "", nextHash);
        }
      }
    },
    [route],
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const onHashChange = () => {
      setRoute(parseWorkbenchHash(window.location.hash));
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const refreshStore = useCallback((): Promise<void> => {
    client
      .modelsCatalog()
      .then((res: ModelCatalogEntry[]) => {
        setModels(res ?? []);
      })
      .catch(() => {
        /* ignore */
      });
    return client
      .documents()
      .then((items: GraphDocument[]) => {
        setDocuments(items ?? []);
        setStoreStatus({ kind: "synced" });
        const preferred =
          items?.find((d: GraphDocument) => d.model_name.toLowerCase().includes("informe")) ?? items?.[0];
        if (preferred) {
          setRoute((prev) => (prev.doc ? prev : { ...prev, doc: preferred.id }));
        }
      })
      .catch((error: unknown) => {
        setStoreStatus({
          kind: "error",
          message: error instanceof Error ? error.message : "SLDB no respondió",
        });
      });
    // Solo depende del cliente: `/graph` trae el store entero y no se vuelve a pedir al navegar.
  }, [client]);

  useEffect(() => {
    void refreshStore();
  }, [refreshStore]);

  // Global keyboard shortcuts (1, 2, 3 lenses + Cmd/Ctrl+K Command Palette)
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((prev) => !prev);
        return;
      }
      if (e.key === "Escape" && paletteOpen) {
        setPaletteOpen(false);
        return;
      }
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      const isEditable =
        tag === "input" ||
        tag === "textarea" ||
        tag === "select" ||
        (e.target as HTMLElement | null)?.isContentEditable;
      if (isEditable || paletteOpen) return;

      if (e.key === "1") {
        navigate({ view: lensTargetView(route.view), lens: "lectura" });
      } else if (e.key === "2") {
        navigate({ view: lensTargetView(route.view), lens: "fierros" });
      } else if (e.key === "3") {
        const activeDoc = documents.find((d) => d.id === route.doc);
        navigate({ view: "studio", model: activeDoc?.model_name ?? route.model });
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate, paletteOpen, documents, route.doc, route.model, route.view]);

  const activeDocItem = useMemo(() => {
    if (route.doc) {
      const clean = route.doc.includes(":") ? route.doc.split(":")[1]! : route.doc;
      const found = documents.find((d) => d.id === route.doc || d.id === clean);
      if (found) return found;
    }
    return (
      documents.find((d) => d.model_name.toLowerCase().includes("informe")) ??
      documents[0] ??
      null
    );
  }, [documents, route.doc]);

  // La wiki de un negocio (un store con su página `NegocioDoc`) se lee en Lectura sin maquinaria:
  // la barra muestra el nombre del negocio; breadcrumb de SLDB, contrato, sync y ⌘K quedan en Fierros.
  const negocio = useMemo(() => businessName(documents), [documents]);
  const esWiki = negocio !== null || models.some((m) => m.name === "NegocioDoc");
  const wikiLectura = esWiki && route.view === "workbench" && route.lens === "lectura";

  useEffect(() => {
    if (typeof document !== "undefined" && negocio) document.title = negocio;
  }, [negocio]);

  const handleSelectLens = (lens: WorkbenchLens | "esquema") => {
    if (lens === "esquema") {
      navigate({ view: "studio", model: activeDocItem?.model_name ?? route.model });
    } else {
      // Lectura / Fierros cambian la lente; solo Esquema (studio) obliga a volver a la prosa.
      navigate({ view: lensTargetView(route.view), lens });
    }
  };

  const filteredPaletteDocs = useMemo(() => {
    const q = paletteQuery.trim().toLowerCase();
    if (!q) return documents;
    return documents.filter(
      (d) =>
        d.id.toLowerCase().includes(q) ||
        docTitle(d).toLowerCase().includes(q) ||
        d.model_name.toLowerCase().includes(q),
    );
  }, [documents, paletteQuery]);

  const filteredPaletteModels = useMemo(() => {
    const q = paletteQuery.trim().toLowerCase();
    if (!q) return models;
    return models.filter((m) => m.name.toLowerCase().includes(q));
  }, [models, paletteQuery]);

  const openPalette = (query: string) => {
    setPaletteQuery(query);
    setPaletteOpen(true);
  };

  const specDocs = useMemo(() => documents.filter((d) => d.model_name === "SpecDoc"), [documents]);
  const sourceDocs = useMemo(
    () => rankSources(documents),
    [documents],
  );

  const crumb = useMemo(() => {
    const bare = (id: string | null | undefined) =>
      id ? (id.includes(":") ? id.slice(id.indexOf(":") + 1) : id) : "—";
    if (route.view === "diagram") {
      return { collection: "SpecDoc", id: bare(route.spec ?? specDocs[0]?.id) };
    }
    if (route.view === "studio") {
      return { collection: "models", id: route.model ?? activeDocItem?.model_name ?? "—" };
    }
    if (route.view === "source") {
      const src = sourceDocs.find((d) => d.id === route.doc) ?? sourceDocs[0];
      return { collection: src?.model_name ?? "—", id: bare(src?.id ?? route.doc) };
    }
    return {
      collection: activeDocItem?.model_name ?? "—",
      id: bare(activeDocItem?.id ?? route.doc),
    };
  }, [route, specDocs, sourceDocs, activeDocItem]);

  const contextPill =
    route.view === "diagram"
      ? "spec2viz · inspector de notación"
      : route.view === "source"
        ? "extracción · anclaje a fuente"
        : route.view === "studio"
          ? "esquema · contrato de modelo"
          : route.lens === "fierros"
            ? "prosa · fierros visibles"
            : "prosa · lectura";

  const openSource = () => {
    const declaredRef = String(
      activeDocItem?.payload?.fuente_ref ?? activeDocItem?.payload?.source ?? "",
    ).trim();
    const declaredBare = declaredRef.includes(":")
      ? declaredRef.slice(declaredRef.indexOf(":") + 1)
      : declaredRef;
    const byDeclared = declaredBare
      ? sourceDocs.find((d) => d.id === declaredRef || d.id === declaredBare)
      : undefined;
    const current = route.doc ?? activeDocItem?.id ?? null;
    const active = byDeclared ?? sourceDocs.find((d) => d.id === current);
    navigate({ view: "source", doc: active?.id ?? sourceDocs[0]?.id ?? route.doc });
  };

  const lensItems: { id: string; label: string; title: string; active: boolean; onSelect: () => void }[] = [
    {
      id: "lectura",
      label: "Lectura",
      title: "Tecla 1: prosa limpia, sin fierros",
      active: route.view !== "studio" && route.lens === "lectura",
      onSelect: () => handleSelectLens("lectura"),
    },
    {
      id: "fierros",
      label: "Estructura / Fierros",
      title: "Tecla 2: canaleta de contratos, autoridad y transclusiones",
      active: route.view !== "studio" && route.lens === "fierros",
      onSelect: () => handleSelectLens("fierros"),
    },
    {
      id: "esquema",
      label: "Esquema",
      title: "Tecla 3: contrato del modelo en Studio",
      active: route.view === "studio",
      onSelect: () => handleSelectLens("esquema"),
    },
  ];

  const contextActions: { label: string; title: string; onSelect: () => void }[] = [];
  if (route.view !== "diagram" && specDocs.length > 0) {
    contextActions.push({
      label: "Spec2Viz ↗",
      title: "Inspector de diagramas SpecDoc",
      onSelect: () => navigate({ view: "diagram" }),
    });
  }
  if (route.view !== "source" && sourceDocs.length > 0) {
    contextActions.push({
      label: "Fuente ↗",
      title: "Extracción y anclaje sobre la FuenteDoc",
      onSelect: openSource,
    });
  }
  if (wikiLectura) {
    contextActions.length = 0;
  } else if (route.view === "workbench" && activeDocItem) {
    contextActions.push({
      label: `contrato ${activeDocItem.model_name} ↗`,
      title: "Abrir el contrato del modelo en Studio",
      onSelect: () => navigate({ view: "studio", model: activeDocItem.model_name }),
    });
  } else if (route.view === "diagram" && (route.spec ?? specDocs[0]?.id)) {
    const specId = route.spec ?? specDocs[0]!.id;
    contextActions.push({
      label: "leer SpecDoc ↗",
      title: "Abrir el SpecDoc como prosa",
      onSelect: () => navigate({ view: "workbench", doc: specId }),
    });
  } else if (route.view === "source" && (route.doc || sourceDocs[0]?.id)) {
    const targetSrc = sourceDocs.find((d) => d.id === route.doc) ?? sourceDocs[0];
    if (targetSrc) {
      contextActions.push({
        label: "leer fuente ↗",
        title: "Abrir la FuenteDoc como prosa",
        onSelect: () => navigate({ view: "workbench", doc: targetSrc.id }),
      });
    }
  } else if (route.view === "studio" && activeDocItem) {
    contextActions.push({
      label: "volver al documento ↗",
      title: "Volver a la prosa del documento activo",
      onSelect: () => navigate({ view: "workbench", doc: activeDocItem.id }),
    });
  }

  return (
    <SldbProvider client={client}>
      <div className="wb-shell" data-testid="sldb-workbench-shell">
        {/* Topbar Stitch (44px): breadcrumb + pill · lentes · acciones + sync + ⌘K */}
        <header className={`wb-topbar ${wikiLectura ? "wb-topbar--wiki" : ""}`} data-testid="wb-topbar">
          {wikiLectura ? (
            <div className="wb-topbar-left">
              <span className="wb-wiki-nombre" data-testid="wiki-business-name">
                {negocio ?? "La wiki de tu negocio"}
              </span>
            </div>
          ) : (
          <div className="wb-topbar-left">
            <nav className="wb-breadcrumb" aria-label="Ruta del documento">
              <span
                className="wb-breadcrumb-root"
                role="button"
                tabIndex={0}
                onClick={() => openPalette("")}
                onKeyDown={(e) => e.key === "Enter" && openPalette("")}
              >
                sldb
              </span>
              <span className="wb-breadcrumb-sep">/</span>
              <span>{crumb.collection}</span>
              <span className="wb-breadcrumb-sep">/</span>
              <button
                type="button"
                className="wb-breadcrumb-active wb-breadcrumb-switch"
                onClick={() => openPalette(crumb.collection === "—" ? "" : crumb.collection)}
                title="Cambiar de documento (⌘K)"
                data-testid="breadcrumb-doc-switch"
              >
                {crumb.id} ▾
              </button>
            </nav>
            <span className="wb-context-pill" data-testid="wb-context-pill">
              {contextPill}
            </span>
          </div>
          )}

          <div className="wb-topbar-right">
            <nav className="wb-lens-nav" aria-label="Lentes del Workbench">
              {wikiLectura && (
                <button
                  type="button"
                  className="wb-lens-link"
                  title="Tecla 2: la estructura de la página y sus metadatos de SLDB"
                  data-testid="wiki-ver-estructura"
                  onClick={() => handleSelectLens("fierros")}
                >
                  Ver estructura
                </button>
              )}
              {!wikiLectura && lensItems.map((item, idx) => (
                <React.Fragment key={item.id}>
                  {idx > 0 && <span className="wb-lens-dot">·</span>}
                  <button
                    type="button"
                    className={`wb-lens-link ${item.active ? "active" : ""}`}
                    aria-pressed={item.active}
                    title={item.title}
                    onClick={item.onSelect}
                  >
                    {item.active ? `[ ${item.label} ]` : item.label}
                  </button>
                </React.Fragment>
              ))}
            </nav>

            {contextActions.map((action) => (
              <button
                key={action.label}
                type="button"
                className="wb-lens-link"
                onClick={action.onSelect}
                title={action.title}
              >
                {action.label}
              </button>
            ))}

            {wikiLectura ? (
              storeStatus.kind === "error" && (
                <span data-testid="sldb-sync-badge" title={storeStatus.message}>
                  Sin conexión con la wiki
                </span>
              )
            ) : (
              <span
                className="wb-mono"
                data-testid="sldb-sync-badge"
                title={storeStatus.kind === "error" ? storeStatus.message : undefined}
              >
                {storeStatus.kind === "synced"
                  ? "[ Sincronizado con .sldb ]"
                  : storeStatus.kind === "loading"
                    ? "[ Leyendo .sldb… ]"
                    : "[ Sin conexión con .sldb ]"}
              </span>
            )}

            {!wikiLectura && <button
              type="button"
              className="wb-btn wb-mono"
              style={{ fontSize: 11, padding: "3px 8px" }}
              onClick={() => openPalette("")}
              data-testid="open-command-palette-btn"
              title="Command Palette"
            >
              ⌘K
            </button>}
          </div>
        </header>

        {/* Active View Body */}
        {route.view === "workbench" && (
          <ProsaWorkbenchView
            key={`ProsaWorkbenchView-${viewEpoch}`}
            docId={activeDocItem?.id ?? route.doc ?? ""}
            documents={documents}
            models={models}
            lens={route.lens}
            onSelectDoc={(docId: string) => navigate({ view: "workbench", doc: docId })}
            onInspectDiagram={(specId: string, nodeDoc?: string) =>
              navigate({ view: "diagram", spec: specId, node: nodeDoc ?? null })
            }
            onOpenSource={(sourceDocId: string) => navigate({ view: "source", doc: sourceDocId })}
            onOpenStudio={(modelName: string) => navigate({ view: "studio", model: modelName })}
            onDocumentsMutated={refreshStore}
          />
        )}

        {route.view === "diagram" && (
          <Spec2VizInspectorView
            key={`Spec2VizInspectorView-${viewEpoch}`}
            client={client}
            documents={documents}
            activeSpecId={route.spec}
            activeNodeDoc={route.node}
            onSelectSpec={(specId: string) => navigate({ view: "diagram", spec: specId, node: null })}
            onSelectNode={(nodeDoc: string | null) => navigate({ view: "diagram", node: nodeDoc })}
            onNavigateToDoc={(docId: string) => navigate({ view: "workbench", doc: docId })}
            onNavigateToSource={(sourceDocId: string) =>
              navigate({ view: "source", doc: sourceDocId })
            }
          />
        )}

        {route.view === "source" && (
          <SourceAnchoringView
            key={`SourceAnchoringView-${viewEpoch}`}
            client={client}
            documents={documents}
            activeSourceId={route.doc}
            onSelectSource={(sourceId: string) => navigate({ view: "source", doc: sourceId })}
            onDocumentsMutated={refreshStore}
            onNavigateToDoc={(docId: string) => navigate({ view: "workbench", doc: docId })}
          />
        )}

        {route.view === "studio" && (
          <ModelStudioView
            key={`ModelStudioView-${viewEpoch}`}
            client={client}
            documents={documents}
            activeModelName={route.model ?? activeDocItem?.model_name ?? null}
            onSelectModel={(modelName: string) => navigate({ view: "studio", model: modelName })}
            onModelsMutated={refreshStore}
          />
        )}

        <WorkbenchAssist
          assistantClient={assistantClient}
          context={{
            view: route.view,
            lens: route.view === "studio" ? null : route.lens,
            doc: activeDocItem?.id ?? route.doc,
            model: route.view === "studio" ? (route.model ?? activeDocItem?.model_name ?? null) : (activeDocItem?.model_name ?? null),
            path: activeDocItem?.path ?? null,
            spec: route.view === "diagram" ? route.spec : null,
            node: route.view === "diagram" ? route.node : null,
          }}
          contextLabel={`${crumb.collection} / ${crumb.id} · ${contextPill}`}
          onStoreChanged={() => {
            refreshStore();
            setViewEpoch((n) => n + 1);
          }}
          onTourGo={(step) => {
            if (step.view) navigate(step.lens ? { view: step.view, lens: step.lens } : { view: step.view });
          }}
        />

        {/* Command Palette Modal (⌘K) */}
        {paletteOpen && (
          <div
            className="wb-palette-backdrop"
            onClick={() => setPaletteOpen(false)}
            data-testid="command-palette-modal"
          >
            <div className="wb-palette-modal" onClick={(e) => e.stopPropagation()}>
              <input
                autoFocus
                className="wb-palette-input"
                placeholder="Buscar documentos (@AtomDoc, InformeDoc), modelos o comandos SLDB..."
                value={paletteQuery}
                onChange={(e) => setPaletteQuery(e.target.value)}
              />
              <div style={{ maxHeight: 360, overflowY: "auto", padding: 8 }}>
                <div className="wb-tree-group-label">Vistas Rápidas</div>
                <div
                  className="wb-tree-item"
                  onClick={() => {
                    navigate({ view: "workbench", lens: "fierros" });
                    setPaletteOpen(false);
                  }}
                >
                  <span>01. Workbench Principal de Prosa y Fierros</span>
                  <span className="wb-mono" style={{ marginLeft: "auto", fontSize: 10 }}>
                    #/workbench
                  </span>
                </div>
                <div
                  className="wb-tree-item"
                  onClick={() => {
                    navigate({ view: "diagram" });
                    setPaletteOpen(false);
                  }}
                >
                  <span>02. Spec2Viz &amp; Notation Inspector</span>
                  <span className="wb-mono" style={{ marginLeft: "auto", fontSize: 10 }}>
                    #/diagram
                  </span>
                </div>
                <div
                  className="wb-tree-item"
                  onClick={() => {
                    navigate({ view: "source" });
                    setPaletteOpen(false);
                  }}
                >
                  <span>03. Extracción y Anclaje a Fuentes (ProseMirror)</span>
                  <span className="wb-mono" style={{ marginLeft: "auto", fontSize: 10 }}>
                    #/source
                  </span>
                </div>
                <div
                  className="wb-tree-item"
                  onClick={() => {
                    navigate({ view: "studio" });
                    setPaletteOpen(false);
                  }}
                >
                  <span>04. Studio de Esquemas y Modelos (CodeMirror 6)</span>
                  <span className="wb-mono" style={{ marginLeft: "auto", fontSize: 10 }}>
                    #/studio
                  </span>
                </div>

                <div className="wb-tree-group-label" style={{ marginTop: 10 }}>
                  Documentos en el Store ({filteredPaletteDocs.length})
                </div>
                {filteredPaletteDocs.map((doc) => (
                  <div
                    key={doc.id}
                    className="wb-tree-item"
                    onClick={() => {
                      // Solo las fuentes nombradas abren en anclaje; el resto se lee como prosa.
                      if (isNamedSourceModel(doc.model_name)) {
                        navigate({ view: "source", doc: doc.id });
                      } else if (doc.model_name === "SpecDoc") {
                        navigate({ view: "diagram", spec: doc.id });
                      } else {
                        navigate({ view: "workbench", doc: doc.id });
                      }
                      setPaletteOpen(false);
                    }}
                  >
                    <span className="wb-mono" style={{ fontSize: 11, color: "var(--wb-ink-muted)" }}>
                      {doc.model_name}:{doc.id}
                    </span>
                    <span style={{ marginLeft: 8 }}>{docTitle(doc)}</span>
                  </div>
                ))}

                <div className="wb-tree-group-label" style={{ marginTop: 10 }}>
                  Contratos de Modelos ({filteredPaletteModels.length})
                </div>
                {filteredPaletteModels.map((m) => (
                  <div
                    key={m.name}
                    className="wb-tree-item"
                    onClick={() => {
                      navigate({ view: "studio", model: m.name });
                      setPaletteOpen(false);
                    }}
                  >
                    <span className="wb-mono" style={{ fontSize: 11 }}>
                      class {m.name}(Document)
                    </span>
                    <span
                      className="wb-mono"
                      style={{ marginLeft: "auto", fontSize: 10, color: "var(--wb-ink-muted)" }}
                    >
                      {m.model_ref}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </SldbProvider>
  );
};
