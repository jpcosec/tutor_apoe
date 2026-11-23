/**
 * GRAFO DE ÁTOMOS (OPERACIONALIZACION-VISTAS.md §3, tabla Grafo).
 *
 * Nodos = átomos no descartados, agrupados en regiones por el primer segmento de su primer tag.
 * Aristas: `relation` (RelationDoc) con flecha y etiqueta; `reference` (estructurales entre
 * átomos) tenues, sin etiqueta y con su propio filtro; `inherited` (extremo-grupo proyectado
 * sobre los miembros) punteadas. Arrastrar de un átomo a otro abre el menú de tipos válidos y
 * crea un `RelationDoc`. También se arrastra DESDE o HASTA el encabezado de una región (o un
 * grupo plegado): la relación es sobre un `GrupoDoc` (se crea si falta) y la heredan los átomos.
 * Crear relaciones es solo con puntero (no hay alternativa de teclado para el arrastre, ni para
 * átomos ni para grupos); el encabezado sí se alcanza con Tab y Enter lo pliega. Toda la lógica (layout, plegado, fusión, geometría) está en
 * `core/atom-graph`; acá solo hay estado de UI y SVG con pointer events.
 *
 * Zoom/pan: rueda para acercar, arrastrar el fondo para mover, "Ajustar" para encuadrar.
 */
import { hrefFor } from "../router";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import {
  IDENTITY_VIEW,
  NO_GROUP,
  assignLanes,
  atomLinks,
  edgeGeometry,
  filterEdges,
  fitView,
  fuseLinks,
  groupOfKey,
  GROUP_KEY_PREFIX,
  highlightKeys,
  isGroupKey,
  layoutRegions,
  nextRelationName,
  nodeAt,
  relationPayloadBetween,
  relationTypeNames,
  screenToWorld,
  truncate,
  wrapLines,
  zoomAt,
  type GraphEdge,
  type LayoutNode,
  type Point,
  type View,
} from "../../core/atom-graph";
import { GROUP_MODEL, groupGid, groupPayload, groupSlug, groupsFromDocuments, isAlreadyExists, tagOfGroupGid } from "../../core/atom-groups";
import { ATOM_MODEL, anchorState, groupTree, validRelationTypesBetween } from "../../core/atoms";
import type { Atom, AtomKind, RelationTypeSpec } from "../../core/contract";
import { useAtomStore } from "./useAtomStore";
import "./atomos-grafo.css";

const KIND_LABEL: Record<AtomKind, string> = { entidad: "Entidad", hecho: "Hecho", decision: "Decisión", pendiente: "Pendiente", riesgo: "Riesgo" };
const KINDS = Object.keys(KIND_LABEL) as AtomKind[];
const ANCHOR_LABEL = { intact: "intacta", drifted: "movida", orphan: "huérfana" } as const;

type Selection = { type: "atom"; id: string } | { type: "edge"; key: string } | null;
/** Extremo de una relación en curso: un átomo o un grupo (`tag` solo en grupos). */
interface End {
  gid: string;
  model: string;
  label: string;
  tag?: string;
}
interface DragState {
  /** Clave de nodo (`AtomDoc:a1`) o de grupo (`group:infra`). */
  sourceKey: string;
  pointer: Point;
}
interface MenuState {
  source: End;
  target: End;
  left: number;
  top: number;
}

/** Coordenadas finitas (jsdom no siempre las entrega en eventos de puntero). */
const clientPoint = (e: { clientX?: number; clientY?: number }): Point => ({
  x: Number.isFinite(e.clientX) ? (e.clientX as number) : 0,
  y: Number.isFinite(e.clientY) ? (e.clientY as number) : 0,
});

export default function AtomosGrafoView({ focusId }: { focusId?: string } = {}) {
  const store = useAtomStore();
  const { status, error, atoms: allAtoms, actas, relationTypes, edges, documents, reload, createDocument } = store;

  const atoms = useMemo(() => allAtoms.filter((a) => a.status !== "descartado"), [allAtoms]);
  const byGid = useMemo(() => new Map(atoms.map((a) => [a.gid, a])), [atoms]);

  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [hiddenTypes, setHiddenTypes] = useState<ReadonlySet<string>>(new Set());
  const [showRefs, setShowRefs] = useState(true);
  const [tag, setTag] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>(focusId ? { type: "atom", id: focusId } : null);
  const [hoverEdge, setHoverEdge] = useState<string | null>(null);
  const [view, setView] = useState<View>(IDENTITY_VIEW);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [notice, setNotice] = useState<{ tone: "error" | "ok"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const wrapRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const dragRef = useRef<DragState | null>(null);
  const panRef = useRef<{ start: Point; view: View } | null>(null);
  const fitted = useRef(false);

  // ------------------------------------------------------------ derivados
  const layout = useMemo(() => layoutRegions(atoms, collapsed), [atoms, collapsed]);
  const links = useMemo(() => atomLinks(edges, atoms), [edges, atoms]);
  const fused = useMemo(() => fuseLinks(links, atoms, collapsed), [links, atoms, collapsed]);
  const shown = useMemo(() => filterEdges(fused, hiddenTypes, showRefs), [fused, hiddenTypes, showRefs]);
  const lanes = useMemo(() => assignLanes(shown), [shown]);
  const typeNames = useMemo(() => relationTypeNames(relationTypes, edges), [relationTypes, edges]);
  const tree = useMemo(() => groupTree(atoms), [atoms]);
  const regionGroups = useMemo(() => new Set(layout.regions.map((r) => r.group)), [layout]);
  const hot = useMemo(() => highlightKeys(atoms, tag, collapsed), [atoms, tag, collapsed]);
  const relationCount = links.filter((l) => l.kind === "relation" && !l.inherited).length;

  const selectedAtom = selection?.type === "atom" ? atoms.find((a) => a.id === selection.id) ?? null : null;
  const selectedEdge = selection?.type === "edge" ? fused.find((e) => e.key === selection.key) ?? null : null;
  const inspectorOpen = selectedAtom !== null || selectedEdge !== null;

  const knownTags = useMemo(() => [...atoms.flatMap((a) => a.tags), ...groupsFromDocuments(documents).map((g) => g.tag)], [atoms, documents]);
  const labelOf = useCallback(
    (key: string): string => {
      if (isGroupKey(key)) return `Grupo ${groupOfKey(key)}`;
      const tagOfGroup = tagOfGroupGid(key, knownTags);
      if (tagOfGroup !== null) return `Grupo ${tagOfGroup}`;
      return byGid.get(key)?.text ?? key;
    },
    [byGid, knownTags],
  );

  /** Extremo de relación para una clave de nodo/grupo; `null` si no se puede relacionar (sin grupo, átomo ausente). */
  const endOfKey = (key: string): End | null => {
    if (isGroupKey(key)) {
      const g = groupOfKey(key);
      return g === NO_GROUP ? null : { gid: groupGid(g), model: GROUP_MODEL, label: `Grupo ${g}`, tag: g };
    }
    const a = byGid.get(key);
    return a ? { gid: a.gid, model: ATOM_MODEL, label: a.text } : null;
  };

  // ------------------------------------------------------------ zoom / pan
  const measure = () => {
    const r = wrapRef.current?.getBoundingClientRect();
    return { width: r?.width ?? 0, height: r?.height ?? 0 };
  };
  const fit = useCallback(() => setView(fitView(layout, measure())), [layout]);

  // Encuadre inicial en cuanto hay tamaño medible y contenido.
  useEffect(() => {
    if (fitted.current || layout.nodes.length === 0) return;
    const apply = () => {
      const size = measure();
      if (size.width > 0 && size.height > 0 && !fitted.current) {
        fitted.current = true;
        setView(fitView(layout, size));
      }
    };
    apply();
    if (typeof ResizeObserver === "undefined" || !wrapRef.current) return;
    const ro = new ResizeObserver(apply);
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, [layout]);

  // La rueda necesita preventDefault: listener nativo no pasivo.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const at = { x: e.clientX - rect.left, y: e.clientY - rect.top };
      setView((v) => zoomAt(v, e.deltaY < 0 ? 1.1 : 1 / 1.1, at));
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  });

  const toWorld = (e: { clientX?: number; clientY?: number }): Point => {
    const rect = svgRef.current?.getBoundingClientRect();
    const p = clientPoint(e);
    return screenToWorld(view, { x: p.x - (rect?.left ?? 0), y: p.y - (rect?.top ?? 0) });
  };

  const zoomBy = (factor: number) => {
    const size = measure();
    setView((v) => zoomAt(v, factor, { x: size.width / 2, y: size.height / 2 }));
  };

  // ------------------------------------------------------------ arrastre para relacionar
  const endDrag = useCallback(() => {
    dragRef.current = null;
    setDrag(null);
  }, []);

  useEffect(() => {
    if (!drag) return;
    // Soltar fuera del SVG cancela.
    window.addEventListener("pointerup", endDrag);
    return () => window.removeEventListener("pointerup", endDrag);
  }, [drag, endDrag]);

  const onNodePointerDown = (e: ReactPointerEvent, node: LayoutNode) => {
    if (e.button > 0) return;
    beginDrag(e, node.key);
  };

  const beginDrag = (e: ReactPointerEvent, key: string) => {
    e.stopPropagation();
    setMenu(null);
    const next = { sourceKey: key, pointer: toWorld(e) };
    dragRef.current = next;
    setDrag(next);
  };

  const onSvgPointerMove = (e: ReactPointerEvent) => {
    if (dragRef.current) {
      const next = { ...dragRef.current, pointer: toWorld(e) };
      dragRef.current = next;
      setDrag(next);
    } else if (panRef.current) {
      const p = clientPoint(e);
      const { start, view: v0 } = panRef.current;
      setView({ ...v0, x: v0.x + p.x - start.x, y: v0.y + p.y - start.y });
    }
  };

  const onSvgPointerUp = (e: ReactPointerEvent) => {
    panRef.current = null;
    const d = dragRef.current;
    if (!d) return;
    endDrag();
    // El elemento bajo el puntero manda; el hit-test geométrico cubre entornos sin hit-testing nativo.
    const el = (e.target as Element).closest?.("[data-node-key],[data-group-head]");
    const head = el?.getAttribute("data-group-head");
    const key = head ? `${GROUP_KEY_PREFIX}${head}` : el?.getAttribute("data-node-key") ?? nodeAt(layout, toWorld(e));
    if (!key || key === d.sourceKey) return; // soltar sobre sí mismo = click
    const source = endOfKey(d.sourceKey);
    const target = endOfKey(key);
    if (!source || !target) {
      if (isGroupKey(key) || isGroupKey(d.sourceKey)) setNotice({ tone: "error", text: `El grupo ${NO_GROUP} no es un grupo real: no admite relaciones.` });
      return;
    }
    if (source.model === GROUP_MODEL && target.model === GROUP_MODEL) {
      setNotice({ tone: "error", text: "No se relaciona un grupo con otro grupo: suelta sobre un átomo." });
      return;
    }
    const wrap = wrapRef.current?.getBoundingClientRect();
    const p = clientPoint(e);
    setNotice(null);
    setMenu({ source, target, left: p.x - (wrap?.left ?? 0), top: p.y - (wrap?.top ?? 0) });
  };

  const onBgPointerDown = (e: ReactPointerEvent) => {
    if (e.button > 0) return;
    panRef.current = { start: clientPoint(e), view };
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
  };

  const create = async (type: RelationTypeSpec) => {
    if (!menu || busy) return;
    const { source, target } = menu;
    setBusy(true);
    const name = nextRelationName(documents);
    try {
      // Un grupo es un documento: se crea la primera vez que recibe una relación (409 = ya existe).
      for (const end of [source, target]) {
        if (!end.tag || documents.some((d) => d.model_name === GROUP_MODEL && `${GROUP_MODEL}:${d.id}` === end.gid)) continue;
        try {
          const g = await createDocument(GROUP_MODEL, groupSlug(end.tag), groupPayload(end.tag));
          if (g && g.ok === false) throw new Error(`El servidor rechazó el grupo ${end.tag}.`);
        } catch (err) {
          if (!isAlreadyExists(err)) throw err;
        }
      }
      const res = await createDocument("RelationDoc", name, relationPayloadBetween(source, target, type));
      if (res && res.ok === false) throw new Error("El servidor rechazó la relación.");
      setNotice({ tone: "ok", text: `Relación ${name} creada: ${type.name}.` });
      setMenu(null);
    } catch (err) {
      // El menú se cierra pero la vista (zoom, plegado, selección) queda como estaba.
      setNotice({ tone: "error", text: `No se creó la relación: ${(err as Error).message}` });
      setMenu(null);
    } finally {
      setBusy(false);
    }
  };

  // ------------------------------------------------------------ acciones
  const toggleGroup = (g: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (!next.delete(g)) next.add(g);
      return next;
    });
  const toggleType = (t: string) =>
    setHiddenTypes((prev) => {
      const next = new Set(prev);
      if (!next.delete(t)) next.add(t);
      return next;
    });
  const selectAtom = (a: Atom) => setSelection({ type: "atom", id: a.id });

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key !== "Escape") return;
    if (menu) setMenu(null);
    else if (drag) endDrag();
    else if (selection) setSelection(null);
    else if (tag) setTag(null);
  };

  // ------------------------------------------------------------ estados
  if (status === "loading" && allAtoms.length === 0) {
    return (
      <div className="atomos-grafo">
        <Header count={null} relations={0} />
        <p className="sidebar__note ag-state" role="status">
          Leyendo el grafo de átomos…
        </p>
      </div>
    );
  }
  if (status === "error" && allAtoms.length === 0) {
    return (
      <div className="atomos-grafo">
        <Header count={null} relations={0} />
        <div className="banner banner--error ag-state" role="alert">
          No se pudo leer el grafo: {error}.{" "}
          <button type="button" className="link-btn" onClick={() => void reload()}>
            Reintentar
          </button>
        </div>
      </div>
    );
  }
  if (atoms.length === 0) {
    return (
      <div className="atomos-grafo">
        <Header count={0} relations={0} />
        <div className="empty-state">
          <h2>Sin átomos todavía</h2>
          <p>
            Los átomos se crean seleccionando texto en una acta (vista Texto). Aquí aparecerán como nodos, agrupados por su primer tag, y podrás
            relacionarlos arrastrando de uno a otro. Los átomos descartados no se dibujan.
          </p>
        </div>
      </div>
    );
  }

  /** Punto de partida de la goma: centro del nodo, o del encabezado de la región si el grupo está desplegado. */
  const originOf = (key: string): Point | null => {
    const n = layout.byKey[key];
    if (n) return { x: n.x + n.w / 2, y: n.y + n.h / 2 };
    const r = isGroupKey(key) ? layout.regions.find((x) => x.group === groupOfKey(key)) : undefined;
    return r ? { x: r.x + r.w / 2, y: r.y + 15 } : null;
  };

  const nodeEls = layout.nodes.map((node) => {
    const atom = node.kind === "atom" ? byGid.get(node.key) : undefined;
    const dim = tag !== null && !hot.has(node.key);
    const isSel = atom !== undefined && selectedAtom?.id === atom.id;
    const isTarget = drag !== null && drag.sourceKey !== node.key && (node.kind === "atom" || !isGroupKey(drag.sourceKey));
    return (
      <NodeView
        key={node.key}
        node={node}
        atom={atom}
        dim={dim}
        selected={isSel}
        source={drag?.sourceKey === node.key}
        droppable={isTarget}
        onPointerDown={(e) => onNodePointerDown(e, node)}
        onActivate={() => (atom ? selectAtom(atom) : toggleGroup(node.group))}
      />
    );
  });

  return (
    <div className="atomos-grafo" onKeyDown={onKeyDown}>
      <Header count={atoms.length} relations={relationCount}>
        <button type="button" className="btn btn--quiet" onClick={fit}>
          Ajustar
        </button>
        <button type="button" className="btn btn--quiet" aria-label="Acercar" onClick={() => zoomBy(1.25)}>
          +
        </button>
        <button type="button" className="btn btn--quiet" aria-label="Alejar" onClick={() => zoomBy(0.8)}>
          −
        </button>
      </Header>

      {status === "error" && (
        <div className="banner banner--error ag-banner" role="alert">
          No se pudo actualizar: {error}.{" "}
          <button type="button" className="link-btn" onClick={() => void reload()}>
            Reintentar
          </button>
        </div>
      )}

      <div className={`ag-body${inspectorOpen ? " ag-body--inspector" : ""}`}>
        <aside className="ag-groups" aria-label="Grupos">
          <h2 className="panel-title">Grupos</h2>
          <ul className="ag-tree">
            {tree.map((g) => (
              <GroupRow
                key={g.id}
                group={g}
                depth={0}
                foldable={regionGroups.has(g.id)}
                collapsed={collapsed.has(g.id)}
                active={tag}
                onToggle={toggleGroup}
                onPick={(id) => setTag((cur) => (cur === id ? null : id))}
              />
            ))}
            {regionGroups.has(NO_GROUP) && (
              <li>
                <div className="ag-group">
                  <span className="ag-group__fold" aria-hidden />
                  <button type="button" className={`ag-group__name${tag === NO_GROUP ? " is-active" : ""}`} onClick={() => setTag((c) => (c === NO_GROUP ? null : NO_GROUP))}>
                    {NO_GROUP}
                  </button>
                  <span className="sidebar__count">{atoms.filter((a) => a.tags.length === 0).length}</span>
                </div>
              </li>
            )}
          </ul>
          {tag && (
            <button type="button" className="link-btn ag-clear" onClick={() => setTag(null)}>
              Quitar resaltado
            </button>
          )}
        </aside>

        <section className="ag-canvas">
          <div className="ag-filters" role="group" aria-label="Filtrar relaciones por tipo">
            {typeNames.map((t) => (
              <button key={t} type="button" className={`tray-filter${hiddenTypes.has(t) ? "" : " is-active"}`} aria-pressed={!hiddenTypes.has(t)} onClick={() => toggleType(t)}>
                {t}
              </button>
            ))}
            <button type="button" className={`tray-filter${showRefs ? " is-active" : ""}`} aria-pressed={showRefs} onClick={() => setShowRefs((s) => !s)}>
              referencias
            </button>
          </div>

          {notice && (
            <div className={`banner ${notice.tone === "error" ? "banner--error" : "banner--ok"} ag-notice`} role={notice.tone === "error" ? "alert" : "status"}>
              {notice.text}{" "}
              <button type="button" className="link-btn" onClick={() => setNotice(null)}>
                Cerrar
              </button>
            </div>
          )}

          <div className="ag-stage" ref={wrapRef}>
            <svg
              ref={svgRef}
              className="ag-svg"
              role="group"
              aria-label="Grafo de átomos"
              onPointerMove={onSvgPointerMove}
              onPointerUp={onSvgPointerUp}
              onClick={(e) => {
                if ((e.target as Element).getAttribute?.("data-bg") !== null) {
                  setSelection(null);
                  setMenu(null);
                }
              }}
            >
              <defs>
                {(["rel", "ref", "hot"] as const).map((v) => (
                  <marker key={v} id={`ag-arrow-${v}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" className={`ag-arrow ag-arrow--${v}`} />
                  </marker>
                ))}
              </defs>
              <rect className="ag-bg" data-bg="" x={-100000} y={-100000} width={200000} height={200000} onPointerDown={onBgPointerDown} />
              <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
                {layout.regions.map((r) => (
                  <g key={r.group} className={`ag-region${tag !== null && !r.nodeKeys.some((k) => hot.has(k)) ? " is-dim" : ""}`}>
                    <rect className="ag-region__box" x={r.x} y={r.y} width={r.w} height={r.h} rx={8} />
                    <g
                      className={`ag-region__head${drag !== null && r.group !== NO_GROUP && drag.sourceKey !== `${GROUP_KEY_PREFIX}${r.group}` && !isGroupKey(drag.sourceKey) ? " is-droppable" : ""}`}
                      role="button"
                      tabIndex={0}
                      aria-label={`${r.collapsed ? "Desplegar" : "Plegar"} región ${r.group}`}
                      data-group-head={r.group === NO_GROUP ? undefined : r.group}
                      onPointerDown={(e) => {
                        if (e.button > 0 || r.group === NO_GROUP) return;
                        beginDrag(e, `${GROUP_KEY_PREFIX}${r.group}`);
                      }}
                      onClick={() => toggleGroup(r.group)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          toggleGroup(r.group);
                        }
                      }}
                    >
                      <rect x={r.x} y={r.y} width={r.w} height={30} fill="transparent" />
                      <text x={r.x + 12} y={r.y + 20} className="ag-region__label">
                        {r.collapsed ? "▸" : "▾"} {r.group} · {r.count}
                      </text>
                    </g>
                  </g>
                ))}

                {shown.map((edge) => {
                  const a = layout.byKey[edge.source];
                  const b = layout.byKey[edge.target];
                  if (!a || !b) return null;
                  const geo = edgeGeometry(a, b, lanes[edge.key] ?? 0, edge.source, edge.target);
                  const isHot = hoverEdge === edge.key || selectedEdge?.key === edge.key || (selectedAtom !== null && (edge.source === selectedAtom.gid || edge.target === selectedAtom.gid));
                  const dim = tag !== null && !hot.has(edge.source) && !hot.has(edge.target);
                  const variant = isHot ? "hot" : edge.kind === "reference" ? "ref" : "rel";
                  const label = edge.count > 1 ? `${edge.type} ×${edge.count}` : edge.type;
                  const name = `${edge.kind === "reference" ? "Referencia" : "Relación"} ${edge.type}${edge.inherited ? " heredada" : ""}: ${labelOf(edge.source)} a ${labelOf(edge.target)}`;
                  return (
                    <g
                      key={edge.key}
                      className={`ag-edge ag-edge--${edge.kind}${edge.inherited ? " is-inherited" : ""}${isHot ? " is-hot" : ""}${dim ? " is-dim" : ""}`}
                      role="button"
                      tabIndex={0}
                      aria-label={name}
                      data-edge-key={edge.key}
                      onPointerEnter={() => setHoverEdge(edge.key)}
                      onPointerLeave={() => setHoverEdge((h) => (h === edge.key ? null : h))}
                      onFocus={() => setHoverEdge(edge.key)}
                      onBlur={() => setHoverEdge((h) => (h === edge.key ? null : h))}
                      onClick={() => setSelection({ type: "edge", key: edge.key })}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setSelection({ type: "edge", key: edge.key });
                        }
                      }}
                    >
                      <path d={geo.d} className="ag-edge__hit" />
                      <path d={geo.d} className="ag-edge__line" markerEnd={`url(#ag-arrow-${variant})`} />
                      {edge.kind === "relation" && (
                        <g transform={`translate(${geo.mid.x} ${geo.mid.y})`}>
                          <text className="ag-edge__label" textAnchor="middle" dy="0.32em">
                            {label}
                          </text>
                        </g>
                      )}
                    </g>
                  );
                })}

                {nodeEls}

                {drag && originOf(drag.sourceKey) && (
                  <line className="ag-rubber" x1={originOf(drag.sourceKey)!.x} y1={originOf(drag.sourceKey)!.y} x2={drag.pointer.x} y2={drag.pointer.y} />
                )}
              </g>
            </svg>

            <div className="ag-legend" aria-label="Leyenda">
              {KINDS.map((k) => (
                <span key={k} className="ag-legend__item">
                  <i className={`ag-dot ag-dot--${k}`} /> {KIND_LABEL[k]}
                </span>
              ))}
              <span className="ag-legend__item">
                <i className="ag-line ag-line--rel" /> relación
              </span>
              <span className="ag-legend__item">
                <i className="ag-line ag-line--inh" /> heredada de grupo
              </span>
              <span className="ag-legend__item">
                <i className="ag-line ag-line--ref" /> referencia
              </span>
            </div>

            <p className="ag-help">
              Arrastra desde un átomo, o desde el encabezado de un grupo, hasta otro átomo para relacionarlos. Si sueltas sobre el encabezado de un grupo (o un grupo plegado), la
              relación la heredan todos sus átomos (línea punteada). Crear relaciones requiere puntero.
            </p>

            {menu && (
              <RelationMenu
                menu={menu}
                types={validRelationTypesBetween(relationTypes, menu.source, menu.target, edges)}
                anyTypes={relationTypes.length > 0}
                busy={busy}
                onPick={(t) => void create(t)}
                onClose={() => setMenu(null)}
              />
            )}
          </div>
        </section>

        {inspectorOpen && (
          <aside className="inspector ag-inspector" aria-label="Inspector">
            <button type="button" className="btn btn--quiet ag-inspector__close" aria-label="Cerrar inspector" onClick={() => setSelection(null)}>
              ×
            </button>
            {selectedAtom && (
              <AtomInspector
                atom={selectedAtom}
                bodyOf={(gid) => actas.find((a) => a.gid === gid)?.body}
                actaIdOf={(gid) => actas.find((a) => a.gid === gid)?.id ?? gid.split(":").slice(1).join(":")}
                links={links}
                byGid={byGid}
                onPick={selectAtom}
              />
            )}
            {selectedEdge && <EdgeInspector edge={selectedEdge} labelOf={labelOf} />}
          </aside>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- piezas

function Header({ count, relations, children }: { count: number | null; relations: number; children?: React.ReactNode }) {
  return (
    <header className="doc-header">
      <div className="doc-header__id">
        <span className="doc-header__model">Grafo de átomos</span>
        {count !== null && (
          <span className="doc-header__path">
            {count} {count === 1 ? "átomo" : "átomos"} · {relations} {relations === 1 ? "relación" : "relaciones"}
          </span>
        )}
      </div>
      {children}
    </header>
  );
}

function GroupRow({
  group,
  depth,
  foldable,
  collapsed,
  active,
  onToggle,
  onPick,
}: {
  group: ReturnType<typeof groupTree>[number];
  depth: number;
  foldable: boolean;
  collapsed: boolean;
  active: string | null;
  onToggle(id: string): void;
  onPick(id: string): void;
}) {
  return (
    <li>
      <div className="ag-group" style={{ paddingLeft: depth * 14 }}>
        {foldable && depth === 0 ? (
          <button type="button" className="ag-group__fold" aria-label={`${collapsed ? "Desplegar" : "Plegar"} grupo ${group.id}`} aria-expanded={!collapsed} onClick={() => onToggle(group.id)}>
            {collapsed ? "▸" : "▾"}
          </button>
        ) : (
          <span className="ag-group__fold" aria-hidden />
        )}
        <button type="button" className={`ag-group__name${active === group.id ? " is-active" : ""}`} aria-pressed={active === group.id} onClick={() => onPick(group.id)}>
          {group.name}
        </button>
        <span className="sidebar__count">{group.count}</span>
      </div>
      {group.children.length > 0 && !collapsed && (
        <ul className="ag-tree">
          {group.children.map((c) => (
            <GroupRow key={c.id} group={c} depth={depth + 1} foldable={false} collapsed={false} active={active} onToggle={onToggle} onPick={onPick} />
          ))}
        </ul>
      )}
    </li>
  );
}

function NodeView({
  node,
  atom,
  dim,
  selected,
  source,
  droppable,
  onPointerDown,
  onActivate,
}: {
  node: LayoutNode;
  atom?: Atom;
  dim: boolean;
  selected: boolean;
  source: boolean;
  droppable: boolean;
  onPointerDown(e: ReactPointerEvent): void;
  onActivate(): void;
}) {
  const kind = atom?.kind ?? "group";
  const lines = wrapLines(atom ? atom.text : `Grupo ${node.group}`, 24, 2);
  const extra = atom ? atom.tags.slice(1, 4) : [];
  const label = atom
    ? `${KIND_LABEL[atom.kind]}: ${atom.text}. Grupo ${node.group}${extra.length ? `, otros tags ${extra.join(", ")}` : ""}. Enter abre el inspector.`
    : `Grupo plegado ${node.group}, ${node.count} átomos. Enter lo despliega.`;
  let chipX = 8;
  return (
    <g
      className={`ag-node ag-node--${kind}${atom ? ` is-${atom.status}` : ""}${dim ? " is-dim" : ""}${selected ? " is-selected" : ""}${source ? " is-source" : ""}${droppable ? " is-droppable" : ""}`}
      transform={`translate(${node.x} ${node.y})`}
      role="button"
      tabIndex={0}
      aria-label={label}
      data-node-key={node.key}
      onPointerDown={onPointerDown}
      onClick={onActivate}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onActivate();
        }
      }}
    >
      <rect className="ag-node__box" width={node.w} height={node.h} rx={6} />
      <rect className="ag-node__bar" width={4} height={node.h} rx={2} />
      {lines.map((l, i) => (
        <text key={i} className="ag-node__text" x={12} y={18 + i * 15}>
          {l}
        </text>
      ))}
      {!atom && (
        <text className="ag-node__chip-text" x={12} y={node.h - 8}>
          {node.count} átomos · clic para desplegar
        </text>
      )}
      {extra.map((t) => {
        const w = Math.min(90, t.length * 5.6 + 10);
        const x = chipX;
        chipX += w + 4;
        return (
          <g key={t} transform={`translate(${x + 4} ${node.h - 17})`}>
            <rect className="ag-node__chip" width={w} height={13} rx={6.5} />
            <text className="ag-node__chip-text" x={w / 2} y={9.5} textAnchor="middle">
              {truncate(t, 15)}
            </text>
          </g>
        );
      })}
    </g>
  );
}

function RelationMenu({
  menu,
  types,
  anyTypes,
  busy,
  onPick,
  onClose,
}: {
  menu: MenuState;
  types: RelationTypeSpec[];
  anyTypes: boolean;
  busy: boolean;
  onPick(t: RelationTypeSpec): void;
  onClose(): void;
}) {
  return (
    <div className="ag-menu" role="menu" aria-label="Tipo de relación" style={{ left: menu.left, top: menu.top }}>
      <p className="ag-menu__title">
        {truncate(menu.source.label, 28)} <span aria-hidden>→</span> {truncate(menu.target.label, 28)}
      </p>
      {(menu.source.tag || menu.target.tag) && (
        <p className="ag-menu__note">Sobre un grupo: la relación la heredan todos sus átomos (línea punteada).</p>
      )}
      {types.length === 0 ? (
        <p className="ag-menu__empty" role="alert">
          {anyTypes
            ? "No hay tipos de relación válidos entre estos dos extremos: los tipos no los admiten (un grupo solo lo admiten los tipos que listan GrupoDoc) o la relación ya existe."
            : "No hay tipos de relación definidos (RelationTypeDoc)."}
        </p>
      ) : (
        types.map((t) => (
          <button key={t.id} type="button" role="menuitem" className="ag-menu__item" disabled={busy} onClick={() => onPick(t)} title={t.description}>
            <strong>{t.name}</strong>
            {t.description && <span>{t.description}</span>}
          </button>
        ))
      )}
      <button type="button" className="btn btn--quiet ag-menu__cancel" onClick={onClose}>
        Cancelar
      </button>
    </div>
  );
}

function AtomInspector({
  atom,
  bodyOf,
  actaIdOf,
  links,
  byGid,
  onPick,
}: {
  atom: Atom;
  bodyOf(gid: string): string | undefined;
  actaIdOf(gid: string): string;
  links: ReturnType<typeof atomLinks>;
  byGid: Map<string, Atom>;
  onPick(a: Atom): void;
}) {
  const body = bodyOf(atom.source);
  const anchor = body === undefined ? null : anchorState(body, atom);
  const rels = links.filter((l) => l.kind === "relation" && (l.source === atom.gid || l.target === atom.gid));
  const actaId = actaIdOf(atom.source);
  return (
    <div className="ag-insp">
      <p className="ag-insp__kind">
        <i className={`ag-dot ag-dot--${atom.kind}`} /> {KIND_LABEL[atom.kind]} · {atom.status}
      </p>
      <h2 className="panel-title">{atom.text}</h2>
      <p className="inspector__note">
        <code>{atom.gid}</code>
      </p>
      {atom.tags.length > 0 && (
        <p className="ag-insp__tags">
          {atom.tags.map((t) => (
            <span key={t} className="tray-tag">
              {t}
            </span>
          ))}
        </p>
      )}
      <h3 className="ag-insp__h">Relaciones</h3>
      {rels.length === 0 ? (
        <p className="inspector__note">Sin relaciones.</p>
      ) : (
        <ul className="ag-insp__rels">
          {rels.map((l, i) => {
            const out = l.source === atom.gid;
            const other = byGid.get(out ? l.target : l.source);
            return (
              <li key={`${l.edge.id}-${i}`}>
                <span aria-label={out ? "saliente" : "entrante"}>{out ? "→" : "←"}</span> <em>{l.edge.type}</em>{" "}
                {other ? (
                  <button type="button" className="link-btn" onClick={() => onPick(other)}>
                    {truncate(other.text, 40)}
                  </button>
                ) : (
                  l.edge.source
                )}
                {l.inherited && (
                  <span className="inspector__note">
                    {" "}
                    (heredada del grupo {l.via}
                    {l.edge.relationDoc ? `, por ${l.edge.relationDoc}` : ""})
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <h3 className="ag-insp__h">Cita</h3>
      <blockquote className="ag-insp__quote">{atom.quote || "(sin cita)"}</blockquote>
      <p className="inspector__note" data-testid="anchor-state">
        Ancla: {anchor ? ANCHOR_LABEL[anchor.state] : "acta no encontrada"}
        {anchor?.state === "drifted" && anchor.movedTo !== undefined && ` (ahora en ${anchor.movedTo})`}
      </p>
      <button type="button" className="btn" onClick={() => (window.location.hash = hrefFor({ view: "atomos-texto", id: actaId, focus: atom.id }))}>
        Ver en el texto
      </button>
    </div>
  );
}

function EdgeInspector({ edge, labelOf }: { edge: GraphEdge; labelOf(key: string): string }) {
  const via = [...new Set(edge.links.map((l) => l.via).filter(Boolean))].join(", ");
  const orig = edge.links[0]?.edge;
  const origin = edge.inherited
    ? `Heredada del grupo ${via || "?"}${edge.relationDocs.length ? ` por la relación ${edge.relationDocs.join(", ")}` : ""}${orig ? ` (${orig.source} → ${orig.target})` : ""}; se calcula, no se guarda.`
    : edge.kind === "reference"
      ? "Referencia estructural (no es un RelationDoc)."
      : "Relación explícita.";
  return (
    <div className="ag-insp">
      <p className="ag-insp__kind">{edge.kind === "reference" ? "Referencia" : "Relación"}</p>
      <h2 className="panel-title">{edge.type}</h2>
      <dl className="ag-insp__dl">
        <dt>Origen</dt>
        <dd>{labelOf(edge.source)}</dd>
        <dt>Destino</dt>
        <dd>{labelOf(edge.target)}</dd>
        <dt>Tipo</dt>
        <dd>{edge.type}</dd>
        <dt>RelationDoc</dt>
        <dd>{edge.relationDocs.length ? edge.relationDocs.join(", ") : "—"}</dd>
      </dl>
      <p className="inspector__note">{origin}</p>
      {edge.count > 1 && (
        <>
          <h3 className="ag-insp__h">Fusiona {edge.count} aristas</h3>
          <ul className="ag-insp__rels">
            {edge.links.map((l, i) => (
              <li key={i}>
                {l.source} → {l.target}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
