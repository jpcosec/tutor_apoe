/**
 * ÁTOMOS EN EL TEXTO · el `body` de un acta con sus átomos subrayados y, al lado, una tarjeta por átomo
 * (OPERACIONALIZACION-VISTAS.md §2). El texto es de solo lectura: los átomos se anclan a él, no lo editan.
 *
 * Toda la lógica de rangos está en `core/atom-text` y `core/atoms`; esta vista solo pinta y llama al store.
 * Descartar no borra: pone `status: "descartado"` y el átomo pasa a la sección "Descartados".
 */
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { checkSelection, effectiveRange, pointOffset, segmentBody, type EffectiveRange, type TextSegment } from "../../core/atom-text";
import { ATOM_KINDS, anchorState, nextAtomName, repairAnchor, selectionToAtomPayload } from "../../core/atoms";
import { SaveConflictError } from "../../core/client";
import type { Acta, AnchorState, Atom, AtomKind } from "../../core/contract";
import { hrefFor } from "../router";
import { useAtomStore, type AtomStore } from "./useAtomStore";
import "./atomos-texto.css";

const KIND_LABEL: Record<AtomKind, string> = { entidad: "Entidad", hecho: "Hecho", decision: "Decisión", pendiente: "Pendiente", riesgo: "Riesgo" };

type SaveState = { status: "idle" } | { status: "saving" } | { status: "saved" } | { status: "error"; message: string } | { status: "conflict"; message: string };

/** Estado de guardado por tarjeta: ejecuta una lista de escrituras de campo en orden. */
function useFieldSaver(saveField: AtomStore["saveField"], atomId: string) {
  const [state, setState] = useState<SaveState>({ status: "idle" });
  const alive = useRef(true);
  useEffect(() => () => void (alive.current = false), []);
  const run = useCallback(
    async (ops: Array<[string, unknown]>) => {
      setState({ status: "saving" });
      try {
        for (const [path, value] of ops) {
          const result = await saveField(atomId, path, value);
          if (!result.ok) throw new Error(result.error ?? "SLDB no guardó el cambio");
        }
        if (alive.current) setState({ status: "saved" });
        return true;
      } catch (error) {
        const message = (error as Error).message;
        if (alive.current) setState(error instanceof SaveConflictError ? { status: "conflict", message } : { status: "error", message });
        return false;
      }
    },
    [saveField, atomId],
  );
  return { state, run, reset: () => setState({ status: "idle" }) };
}

interface CardProps {
  atom: Atom;
  body: string;
  store: AtomStore;
  active: boolean;
  dim: boolean;
  onFocus(id: string): void;
  onHover(id: string | null): void;
}

function SaveLine({ state, onReload }: { state: SaveState; onReload(): void }) {
  if (state.status === "saving") return <span className="atx-card__meta" role="status">Guardando…</span>;
  if (state.status === "saved") return <span className="atx-card__meta" role="status">Guardado</span>;
  if (state.status === "error") return <div className="atx-error" role="alert">No se guardó: {state.message}</div>;
  if (state.status === "conflict")
    return (
      <div className="atx-error" role="alert">
        El átomo cambió en SLDB; no se escribió nada.
        <button type="button" className="btn" onClick={onReload}>Recargar</button>
      </div>
    );
  return null;
}

function AtomCard({ atom, body, store, active, dim, onFocus, onHover }: CardProps) {
  const { state, run } = useFieldSaver(store.saveField, atom.id);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(atom.text);
  const check = useMemo(() => anchorState(body, atom), [body, atom]);
  const discarded = atom.status === "descartado";
  const busy = state.status === "saving";
  const cardRef = useRef<HTMLElement>(null);

  const onKey = (event: KeyboardEvent<HTMLElement>) => {
    if (event.target === event.currentTarget && event.key === "Enter") {
      event.preventDefault();
      onFocus(atom.id);
    }
  };
  const saveText = async () => {
    const text = draft.trim();
    if (!text || text === atom.text) return setEditing(false);
    if (await run([["text", text]])) setEditing(false);
  };
  const repair = () => {
    const fixed = repairAnchor(body, atom);
    if (fixed) void run([["start", fixed.start], ["end", fixed.end]]);
  };

  return (
    <article
      ref={cardRef}
      data-atom-card={atom.id}
      className={`atx-card atx-k-${atom.kind}${active ? " is-active" : ""}${dim ? " is-dim" : ""}${discarded ? " is-discarded" : ""}`}
      tabIndex={0}
      aria-label={`Átomo ${atom.id}: ${atom.text}`}
      aria-current={active ? "true" : undefined}
      onClick={() => onFocus(atom.id)}
      onKeyDown={onKey}
      onMouseEnter={() => onHover(atom.id)}
      onMouseLeave={() => onHover(null)}
    >
      <div className="atx-card__row">
        <span className="atx__dot" aria-hidden="true" />
        <select
          className="atx-card__kind"
          aria-label={`Tipo del átomo ${atom.id}`}
          value={atom.kind}
          disabled={busy}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => void run([["kind", e.target.value]])}
        >
          {ATOM_KINDS.map((k) => (
            <option key={k} value={k}>{KIND_LABEL[k]}</option>
          ))}
        </select>
        <span className={`atx-badge${atom.status === "confirmado" ? " atx-badge--ok" : ""}`}>{atom.status}</span>
        <span className="atx-card__meta" title="Confianza de la extracción">{Math.round(atom.conf * 100)}%</span>
        <span className="atx__spacer" />
        <SaveLine state={{ status: state.status === "saving" || state.status === "saved" ? state.status : "idle" }} onReload={() => void store.reload()} />
      </div>

      {editing ? (
        <div className="atx-edit" onClick={(e) => e.stopPropagation()}>
          <input
            aria-label={`Texto del átomo ${atom.id}`}
            value={draft}
            autoFocus
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void saveText();
              if (e.key === "Escape") setEditing(false);
            }}
          />
          <button type="button" className="btn btn--primary" disabled={busy} onClick={() => void saveText()}>Guardar texto</button>
          <button type="button" className="btn" onClick={() => setEditing(false)}>Cancelar</button>
        </div>
      ) : (
        <p className="atx-card__text">{atom.text}</p>
      )}

      {atom.tags.length > 0 && (
        <div className="atx-card__row" aria-label="Tags">
          {atom.tags.map((tag) => (
            <span key={tag} className="atx-tag">{tag}</span>
          ))}
        </div>
      )}
      {atom.quote && <p className="atx-card__quote">«{atom.quote}»</p>}

      {check.state === "drifted" && (
        <div className="atx-warn">
          <span>Ancla movida: la cita ya no está en {atom.start}–{atom.end}.</span>
          <button type="button" className="btn" disabled={busy} onClick={(e) => { e.stopPropagation(); repair(); }}>Reparar ancla</button>
        </div>
      )}
      {check.state === "orphan" && <div className="atx-warn">El texto cambió: la cita ya no aparece en el acta.</div>}

      <SaveLine state={state.status === "error" || state.status === "conflict" ? state : { status: "idle" }} onReload={() => void store.reload()} />

      <div className="atx-card__row" onClick={(e) => e.stopPropagation()}>
        {discarded ? (
          <button type="button" className="btn" disabled={busy} onClick={() => void run([["status", "propuesto"]])}>Restaurar</button>
        ) : (
          <>
            <button type="button" className="btn btn--primary" disabled={busy || atom.status === "confirmado"} onClick={() => void run([["status", "confirmado"]])}>Confirmar</button>
            <button type="button" className="btn" disabled={busy} onClick={() => void run([["status", "descartado"]])}>Descartar</button>
            <button type="button" className="btn btn--quiet" disabled={busy} onClick={() => { setDraft(atom.text); setEditing(true); }}>Editar texto</button>
          </>
        )}
        <button type="button" className="btn btn--quiet" onClick={() => { window.location.hash = hrefFor({ view: "atomos-grafo", focus: atom.id }); }}>Ver en el grafo</button>
      </div>
    </article>
  );
}

// ---------------------------------------------------------------- texto fuente

interface MarkInfo {
  atom: Atom;
  anchor: AnchorState;
}

/** Offset global de un punto (nodo, desplazamiento) de un Range dentro del cuerpo; `null` si cae fuera. */
function domPointToOffset(root: HTMLElement, node: Node, offset: number): number | null {
  if (!root.contains(node)) return null;
  const startOf = (el: Element | null) => {
    const host = el?.closest("[data-start]");
    return host && root.contains(host) ? Number(host.getAttribute("data-start")) : null;
  };
  if (node.nodeType === Node.TEXT_NODE) {
    const base = startOf(node.parentElement);
    return base === null ? null : pointOffset(base, offset);
  }
  const el = node as Element;
  const child = el.childNodes[offset];
  if (child) {
    if (child.nodeType === Node.TEXT_NODE) return domPointToOffset(root, child, 0);
    const c = child as Element;
    const own = c.closest("[data-start]") ?? c.querySelector("[data-start]");
    return own && root.contains(own) ? Number(own.getAttribute("data-start")) : null;
  }
  const host = el.closest("[data-end]");
  return host && root.contains(host) ? Number(host.getAttribute("data-end")) : null;
}

interface Pending {
  from: number;
  to: number;
  top: number;
  left: number;
}

// ---------------------------------------------------------------- vista

function ActaAtoms({ acta, store, initialFocus }: { acta: Acta; store: AtomStore; initialFocus?: string }) {
  const { body } = acta;
  const [kinds, setKinds] = useState<AtomKind[]>([]);
  const [lowFirst, setLowFirst] = useState(false);
  const [focusId, setFocusId] = useState<string | null>(initialFocus ?? null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const sourceRef = useRef<HTMLDivElement>(null);
  const scrollTarget = useRef<"card" | "text" | null>(null);

  const mine = useMemo(() => store.atoms.filter((a) => a.source === acta.gid), [store.atoms, acta.gid]);
  const live = useMemo(() => mine.filter((a) => a.status !== "descartado"), [mine]);
  const discarded = useMemo(() => mine.filter((a) => a.status === "descartado"), [mine]);
  const unconfirmed = live.filter((a) => a.status !== "confirmado").length;
  const kindOk = useCallback((a: Atom) => kinds.length === 0 || kinds.includes(a.kind), [kinds]);

  const visible = useMemo(() => live.filter(kindOk), [live, kindOk]);
  const marks = useMemo(() => new Map<string, MarkInfo>(visible.map((a) => [a.id, { atom: a, anchor: anchorState(body, a).state }])), [visible, body]);
  const ranges = useMemo(() => visible.map((a) => effectiveRange(body, a)).filter((r): r is EffectiveRange => r !== null), [visible, body]);
  const paragraphs = useMemo(() => segmentBody(body, ranges), [body, ranges]);

  const cards = useMemo(() => {
    const list = [...visible];
    list.sort(lowFirst ? (a, b) => a.conf - b.conf || a.start - b.start : (a, b) => a.start - b.start);
    return list;
  }, [visible, lowFirst]);

  const active = focusId ?? hoverId;

  const focus = useCallback((id: string, from: "card" | "text") => {
    scrollTarget.current = from === "text" ? "card" : "text";
    setFocusId((prev) => (prev === id && from === "text" ? prev : id));
  }, []);

  useEffect(() => {
    if (!focusId || !scrollTarget.current) return;
    const where = scrollTarget.current;
    scrollTarget.current = null;
    const root = where === "card" ? document : sourceRef.current;
    const el = where === "card" ? root?.querySelector(`[data-atom-card="${focusId}"]`) : root?.querySelector(`[data-atom-mark="${focusId}"]`);
    (el as HTMLElement | null | undefined)?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
    if (where === "card") (el as HTMLElement | null | undefined)?.focus?.({ preventScroll: true });
  }, [focusId, cards.length]);

  const readSelection = () => {
    const root = sourceRef.current;
    const sel = window.getSelection();
    if (!root || !sel || sel.rangeCount === 0 || sel.isCollapsed) return setPending(null);
    const range = sel.getRangeAt(0);
    if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return setPending(null);
    const from = domPointToOffset(root, range.startContainer, range.startOffset);
    const to = domPointToOffset(root, range.endContainer, range.endOffset);
    if (from === null || to === null) return setPending(null);
    const check = checkSelection(body, from, to);
    if (!check.ok) {
      setPending(null);
      setNotice(check.reason);
      return;
    }
    setNotice(null);
    const rect = range.getBoundingClientRect?.();
    setPending({ from: check.from, to: check.to, top: rect?.top ?? 0, left: rect ? rect.left + rect.width / 2 : 0 });
  };

  const create = async () => {
    if (!pending) return;
    const name = nextAtomName(store.atoms.map((a) => a.id));
    setCreating(true);
    try {
      const result = await store.createAtom(name, selectionToAtomPayload(body, pending.from, pending.to, "hecho", acta.gid));
      setPending(null);
      setNotice(null);
      window.getSelection()?.removeAllRanges();
      focus(result.id || name, "text");
    } catch (error) {
      setNotice(`No se creó el átomo: ${(error as Error).message}`);
    } finally {
      setCreating(false);
    }
  };

  const renderSegment = (seg: TextSegment): ReactNode => {
    // Cada átomo es un span anidado: los bordes inferiores se apilan.
    let node: ReactNode = seg.text;
    for (const id of [...seg.atomIds].reverse()) {
      const info = marks.get(id);
      if (!info) continue;
      const { atom, anchor } = info;
      const isActive = active === id;
      const cls = [
        "atx-mark",
        `atx-k-${atom.kind}`,
        atom.status === "confirmado" ? "is-confirmed" : "is-proposed",
        anchor === "drifted" ? "is-moved" : "",
        isActive ? "is-active" : active ? "is-dim" : "",
      ].filter(Boolean).join(" ");
      node = (
        <span
          className={cls}
          data-atom-mark={id}
          data-status={atom.status}
          data-anchor={anchor}
          title={`${KIND_LABEL[atom.kind]} · ${atom.status}${anchor === "drifted" ? " · movida" : ""}`}
          onMouseEnter={() => setHoverId(id)}
          onMouseLeave={() => setHoverId(null)}
          onClick={(e) => {
            if (window.getSelection()?.isCollapsed === false) return;
            e.stopPropagation();
            focus(id, "text");
          }}
        >
          {node}
        </span>
      );
    }
    return (
      <span key={seg.start} data-start={seg.start} data-end={seg.end}>
        {node}
      </span>
    );
  };

  const toggleKind = (kind: AtomKind) => setKinds((prev) => (prev.includes(kind) ? prev.filter((k) => k !== kind) : [...prev, kind]));
  const count = (kind: AtomKind) => live.filter((a) => a.kind === kind).length;

  return (
    <div className="atx">
      <header className="atx__head">
        <h2 className="atx__title">{acta.title}</h2>
        <span className="atx__count" role="status">
          {live.length} {live.length === 1 ? "átomo" : "átomos"}, {unconfirmed} sin confirmar
        </span>
        <div className="atx__filters" role="group" aria-label="Filtrar por tipo">
          {ATOM_KINDS.map((kind) => (
            <button key={kind} type="button" className={`atx__filter atx-k-${kind}`} aria-pressed={kinds.includes(kind)} onClick={() => toggleKind(kind)}>
              <span className="atx__dot" aria-hidden="true" />
              {KIND_LABEL[kind]} {count(kind)}
            </button>
          ))}
        </div>
        <label className="atx__check">
          <input type="checkbox" checked={lowFirst} onChange={(e) => setLowFirst(e.target.checked)} />
          Baja confianza primero
        </label>
        <span className="atx__spacer" />
        <button type="button" className="btn" disabled title="Falta el extractor: aún no existe endpoint">
          Re-extraer lo no confirmado
        </button>
      </header>

      {notice && (
        <p className="atx-warn atx__notice" role="alert">
          {notice}
        </p>
      )}
      {store.status === "error" && (
        <p className="atx-error atx__notice" role="alert">
          No se pudo actualizar desde SLDB: {store.error}
          <button type="button" className="btn" onClick={() => void store.reload()}>Reintentar</button>
        </p>
      )}

      <div className="atx__grid">
        <div
          className="atx__source"
          ref={sourceRef}
          role="region"
          aria-label="Texto fuente (solo lectura)"
          onMouseUp={readSelection}
          onKeyUp={readSelection}
        >
          {paragraphs.length === 0 ? (
            <p className="atx-source-empty">El acta no tiene texto.</p>
          ) : (
            paragraphs.map((p) => (
              <p key={p.start} data-start={p.start} data-end={p.end}>
                {p.segments.map((s) => (
                  <Fragment key={s.start}>{renderSegment(s)}</Fragment>
                ))}
              </p>
            ))
          )}
        </div>

        <aside className="atx__panel" aria-label="Átomos del acta">
          {cards.length === 0 && (
            <p className="atx__state">{mine.length === 0 ? "Esta acta aún no tiene átomos. Selecciona texto para crear uno." : "Ningún átomo coincide con el filtro."}</p>
          )}
          {cards.map((atom) => (
            <AtomCard
              key={atom.id}
              atom={atom}
              body={body}
              store={store}
              active={active === atom.id}
              dim={active !== null && active !== atom.id}
              onFocus={(id) => focus(id, "card")}
              onHover={setHoverId}
            />
          ))}
          {discarded.filter(kindOk).length > 0 && (
            <details className="atx__discarded">
              <summary>Descartados ({discarded.filter(kindOk).length})</summary>
              <div className="atx__discarded-list">
                {discarded.filter(kindOk).map((atom) => (
                  <AtomCard key={atom.id} atom={atom} body={body} store={store} active={false} dim={false} onFocus={() => undefined} onHover={() => undefined} />
                ))}
              </div>
            </details>
          )}
        </aside>
      </div>

      {pending && (
        <button
          type="button"
          className="btn btn--primary atx-floating"
          style={{ top: pending.top, left: pending.left }}
          disabled={creating}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => void create()}
        >
          Crear átomo desde la selección
        </button>
      )}
    </div>
  );
}

export default function AtomosTextoView({ actaId, focusId }: { actaId: string; focusId?: string }) {
  const store = useAtomStore();
  const acta = store.actas.find((a) => a.id === actaId);

  if (!acta) {
    if (store.status === "loading") return <div className="atx__state" role="status">Cargando átomos…</div>;
    if (store.status === "error")
      return (
        <div className="atx__state" role="alert">
          <p>No se pudo cargar desde SLDB: {store.error}</p>
          <button type="button" className="btn" onClick={() => void store.reload()}>Reintentar</button>
        </div>
      );
    return <div className="empty-state">No existe el acta «{actaId}».</div>;
  }
  return <ActaAtoms acta={acta} store={store} initialFocus={focusId} />;
}
