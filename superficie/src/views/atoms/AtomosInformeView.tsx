/**
 * INFORME · slots fijos con consulta, pins y exclusiones (OPERACIONALIZACION-VISTAS §3 Compositor y §4).
 * Lógica en `core/atoms` y `core/atom-report`; acá solo estado de vista y presentación.
 * Los `nuevos` de Actualizar viven en el estado de la vista: no se persisten hasta aceptarlos.
 */
import { useMemo, useState } from "react";
import { acceptAtom, anchorState, excludeAtom, matchQuery, pinAtom, refreshSlot, SLOT_MODES, SLOT_NAMES, unexcludeAtom, unpinAtom, type SlotRefresh } from "../../core/atoms";
import {
  buildPreview,
  nextVersion,
  parseQuery,
  publicationName,
  publicationPayload,
  publicationsOf,
  PUBLICATION_MODEL,
  publishState,
  removeQueryToken,
  reviewGate,
  SLOT_LABELS,
  slotChanges,
  slotField,
  snapshotAtoms,
  type PreviewItem,
  type PreviewSection,
} from "../../core/atom-report";
import { SaveConflictError } from "../../core/client";
import type { Atom, InformeSlot, SlotMode, SlotName } from "../../core/contract";
import { useSldb } from "../../react/context";
import { hrefFor } from "../router";
import { useAtomStore } from "./useAtomStore";
import "./atomos-informe.css";

const KIND_LABEL: Record<string, string> = { entidad: "Entidad", hecho: "Hecho", decision: "Decisión", pendiente: "Pendiente", riesgo: "Riesgo" };
const MODE_HELP = "El documento guardado en disco renderiza siempre viñetas (así lo compone SLDB hoy); prosa y tabla son solo vista previa.";

interface Failure {
  message: string;
  conflict: boolean;
}

const textHref = (atom: Atom) => hrefFor({ view: "atomos-texto", id: atom.source.split(":").slice(1).join(":") || atom.source, focus: atom.id });

export default function AtomosInformeView({ informeId }: { informeId: string }) {
  const store = useAtomStore();
  const { client } = useSldb();
  const { status, atoms, actas, informes, edges, documents, saveField, reload } = store;
  const informe = informes.find((i) => i.id === informeId);

  const [selected, setSelected] = useState<SlotName>("resumen");
  const [drafts, setDrafts] = useState<Partial<Record<SlotName, string>>>({});
  const [refreshes, setRefreshes] = useState<Partial<Record<SlotName, SlotRefresh>>>({});
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [provenance, setProvenance] = useState<PreviewItem | null>(null);
  const [publishing, setPublishing] = useState(false);

  const byPath = useMemo(() => new Map(atoms.map((a) => [a.path, a])), [atoms]);
  const bodyOf = useMemo(() => new Map(actas.map((a) => [a.gid, a.body])), [actas]);
  const preview = useMemo(() => (informe ? buildPreview(informe.slots, atoms, edges) : []), [informe, atoms, edges]);

  if (!informe) {
    if (status === "loading") return <div className="empty-state" role="status">Cargando informe…</div>;
    if (status === "error")
      return (
        <div className="empty-state">
          <div className="banner banner--error" role="alert">
            No se pudo leer el store: {store.error}.{" "}
            <button type="button" className="link-btn" onClick={() => void reload()}>
              Reintentar
            </button>
          </div>
        </div>
      );
    return (
      <div className="empty-state">
        <h2>No existe el informe {informeId}</h2>
        <p>Revisa el identificador o crea el informe desde SLDB.</p>
      </div>
    );
  }

  const nuevosBySlot = Object.fromEntries(SLOT_NAMES.map((s) => [s, refreshes[s]?.nuevos ?? []]));
  const gate = reviewGate(nuevosBySlot);
  const slot = informe.slots[selected];
  const queryText = drafts[selected] ?? slot.query;
  const parsed = parseQuery(queryText);
  const publications = publicationsOf(documents, informe.id);
  const publish = publishState({ gate, publications, atomCount: snapshotAtoms(informe.slots).length, publishing });
  const title = typeof informe.payload.title === "string" && informe.payload.title ? informe.payload.title : `Informe ${informe.id}`;

  /** Ejecuta escrituras; si el servidor las rechaza, no se aplica nada en pantalla (la vista sale del store) y se relee. */
  async function run(work: () => Promise<void>): Promise<boolean> {
    setBusy(true);
    setFailure(null);
    setSaved(false);
    try {
      await work();
      setSaved(true);
      return true;
    } catch (error) {
      setFailure({ message: (error as Error).message, conflict: error instanceof SaveConflictError });
      await reload();
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function write(field: string, value: unknown) {
    const result = await saveField(informe!.id, field, value);
    if (!result.ok) throw new Error(result.error ?? "El servidor rechazó el cambio.");
  }

  async function change(name: SlotName, next: InformeSlot): Promise<boolean> {
    return run(async () => {
      for (const c of slotChanges(name, informe!.slots[name], next)) await write(c.field, c.value);
    });
  }

  async function saveQuery(name: SlotName, text: string) {
    if (text === informe!.slots[name].query) {
      setDrafts((d) => ({ ...d, [name]: undefined }));
      return;
    }
    const ok = await run(() => write(slotField(name, "query"), text));
    if (ok) setDrafts((d) => ({ ...d, [name]: undefined }));
  }

  async function setMode(name: SlotName, modo: SlotMode) {
    await run(() => write(slotField(name, "modo"), modo));
  }

  function update() {
    const pool = atoms.filter((a) => a.status !== "descartado");
    const results = matchQuery(pool, parsed.filters).map((a) => a.path);
    setRefreshes((r) => ({ ...r, [selected]: refreshSlot(slot, results) }));
  }

  const dropNuevo = (name: SlotName, path: string) =>
    setRefreshes((r) => (r[name] ? { ...r, [name]: { ...r[name]!, nuevos: r[name]!.nuevos.filter((p) => p !== path) } } : r));

  async function decideNuevo(path: string, fn: typeof acceptAtom) {
    const name = selected;
    if (await change(name, fn(informe!.slots[name], path))) dropNuevo(name, path);
  }

  /** Crea la foto inmutable: lee el render real y las versiones frescas del servidor; si otro publicó a la vez (409) reintenta una vez. */
  async function publishNow() {
    setPublishing(true);
    setFailure(null);
    setSaved(false);
    const attempt = async () => {
      const [docs, markdown] = await Promise.all([client.documents(), client.render(informe!.id)]);
      const version = nextVersion(publicationsOf(docs, informe!.id));
      return client.createDocument(PUBLICATION_MODEL, publicationName(informe!.id, version), publicationPayload({ informe: informe!, version, markdown }));
    };
    try {
      try {
        await attempt();
      } catch (error) {
        if (!(error instanceof SaveConflictError)) throw error;
        await attempt();
      }
    } catch (error) {
      const conflict = error instanceof SaveConflictError;
      setFailure({ message: conflict ? "Otra publicación ganó de mano dos veces; vuelve a intentarlo." : `No se pudo publicar: ${(error as Error).message}`, conflict: false });
    } finally {
      await reload();
      setPublishing(false);
    }
  }

  const nuevos = refreshes[selected]?.nuevos ?? [];
  const salieron = refreshes[selected]?.salieron ?? [];

  const renderAtomCard = (path: string, mode: "lista" | "excluido") => {
    const atom = byPath.get(path);
    const pinned = slot.pins.includes(path);
    if (!atom)
      return (
        <li key={path} className="inf-card inf-card--missing">
          <p className="inf-card__text">Átomo no encontrado: <code>{path}</code></p>
          {mode === "lista" ? (
            <button type="button" className="btn btn--quiet" disabled={busy} onClick={() => void change(selected, excludeAtom(slot, path))}>
              Excluir
            </button>
          ) : null}
        </li>
      );
    const body = bodyOf.get(atom.source);
    const orphan = body !== undefined && anchorState(body, atom).state === "orphan";
    const left = salieron.includes(path);
    const label = mode === "excluido" ? "Excluido a mano" : pinned ? "Fijado a mano" : "Por consulta";
    return (
      <li key={path} className="inf-card">
        <div className="inf-card__head">
          <span className="inf-kind">{KIND_LABEL[atom.kind] ?? atom.kind}</span>
          <span className={`inf-tag inf-tag--${mode === "excluido" ? "excluded" : pinned ? "pinned" : "query"}`}>{label}</span>
          {left && <span className="inf-tag inf-tag--warn">Ya no calza con la consulta</span>}
          {orphan && <span className="inf-tag inf-tag--danger">ancla rota</span>}
        </div>
        <p className="inf-card__text">{atom.text}</p>
        <div className="inf-card__actions">
          {mode === "lista" ? (
            <>
              <button type="button" className="btn btn--quiet" disabled={busy} onClick={() => void change(selected, pinned ? unpinAtom(slot, path) : pinAtom(slot, path))}>
                {pinned ? "Soltar pin" : "Fijar"}
              </button>
              <button type="button" className="btn btn--quiet" disabled={busy} onClick={() => void change(selected, excludeAtom(slot, path))}>
                Excluir
              </button>
            </>
          ) : (
            <button type="button" className="btn btn--quiet" disabled={busy} onClick={() => void change(selected, unexcludeAtom(slot, path))}>
              Volver a incluir
            </button>
          )}
          <a className="link-btn" href={textHref(atom)}>
            Origen
          </a>
        </div>
      </li>
    );
  };

  const openItem = (item: PreviewItem) => setProvenance(item);

  return (
    <div className="inf-view">
      <header className="inf-bar">
        <h2 className="inf-bar__title">{title}</h2>
        <span className={`inf-gate inf-gate--${gate.ready ? "ready" : "pending"}`} role="status">
          {gate.label}
        </span>
        <span className={`inf-published${publications.length ? "" : " inf-published--none"}`}>{publish.published}</span>
        {publications.length > 0 && (
          <details className="inf-versions">
            <summary>Versiones</summary>
            <ul aria-label="Versiones publicadas">
              {[...publications].reverse().map((p) => (
                <li key={p.id}>
                  <a className="link-btn" href={hrefFor({ view: "doc", id: p.id, mode: "document" })}>
                    v{p.version}
                  </a>{" "}
                  <span className="inf-help">{p.atoms.length} {p.atoms.length === 1 ? "átomo" : "átomos"}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
        <span className="save-status" role="status" aria-live="polite">
          {publishing ? "Publicando…" : busy ? "Guardando…" : saved ? "Guardado" : ""}
        </span>
        <button type="button" className="btn btn--primary" disabled={!publish.enabled || busy} title={publish.reason || undefined} onClick={() => void publishNow()}>
          {publish.label}
        </button>
      </header>

      {failure && (
        <div className="banner banner--error" role="alert">
          <p>{failure.conflict ? "El informe cambió en SLDB desde que lo abriste; no se escribió nada." : failure.message}</p>
          <div className="banner__actions">
            {failure.conflict && (
              <button type="button" className="btn btn--primary" onClick={() => void reload().then(() => setFailure(null))}>
                Recargar informe
              </button>
            )}
            <button type="button" className="btn" onClick={() => setFailure(null)}>
              Cerrar
            </button>
          </div>
        </div>
      )}

      <div className="inf-cols">
        <nav className="inf-col inf-skeleton" aria-label="Esqueleto">
          <h3>Esqueleto</h3>
          <ul>
            {SLOT_NAMES.map((name) => (
              <li key={name}>
                <button type="button" className={`inf-slot${name === selected ? " inf-slot--on" : ""}`} aria-current={name === selected ? "true" : undefined} onClick={() => setSelected(name)}>
                  <span>{SLOT_LABELS[name]}</span>
                  {(nuevosBySlot[name]?.length ?? 0) > 0 && <span className="inf-dot" role="img" aria-label="Tiene átomos nuevos" />}
                  <span className="inf-count" aria-label={`${informe.slots[name].atomos.length} incluidos en ${SLOT_LABELS[name]}`}>
                    {informe.slots[name].atomos.length}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <p className="sidebar__note">Las secciones las define el tipo de informe.</p>
        </nav>

        <section className="inf-col inf-editor" aria-label={`Slot ${SLOT_LABELS[selected]}`}>
          <h3>{SLOT_LABELS[selected]}</h3>
          <label className="inf-field">
            <span>Qué va en este slot</span>
            <input
              type="text"
              value={queryText}
              placeholder="tipo:decision tag:infra estado:confirmado texto libre"
              onChange={(e) => setDrafts((d) => ({ ...d, [selected]: e.target.value }))}
              onBlur={(e) => void saveQuery(selected, e.target.value)}
            />
          </label>
          {parsed.tokens.some((t) => t.kind !== "texto") && (
            <ul className="inf-chips" aria-label="Filtros">
              {parsed.tokens.map((t, i) =>
                t.kind === "texto" ? null : (
                  <li key={`${t.raw}-${i}`} className={`inf-chip${t.active ? "" : " inf-chip--off"}`} title={t.active ? undefined : "Este filtro no se aplica"}>
                    {t.raw}
                    <button
                      type="button"
                      aria-label={`Quitar filtro ${t.raw}`}
                      onClick={() => {
                        const next = removeQueryToken(queryText, i);
                        setDrafts((d) => ({ ...d, [selected]: next }));
                        void saveQuery(selected, next);
                      }}
                    >
                      ✕
                    </button>
                  </li>
                ),
              )}
            </ul>
          )}
          <div className="inf-row">
            <label className="inf-field inf-field--inline">
              <span>Presentar como</span>
              <select value={slot.modo} disabled={busy} onChange={(e) => void setMode(selected, e.target.value as SlotMode)}>
                {SLOT_MODES.map((m) => (
                  <option key={m} value={m}>
                    {m === "viñetas" ? "Viñetas" : m === "prosa" ? "Prosa" : "Tabla"}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="btn" onClick={update}>
              Actualizar
            </button>
          </div>
          <p className="inf-help">{MODE_HELP}</p>

          {refreshes[selected] && nuevos.length === 0 && salieron.length === 0 && <p className="inf-help">La consulta no trae cambios.</p>}
          {salieron.length > 0 && (
            <div className="banner" role="status">
              {salieron.length} {salieron.length === 1 ? "átomo de la lista ya no calza" : "átomos de la lista ya no calzan"} con la consulta. Siguen en el informe hasta que los excluyas.
            </div>
          )}
          {nuevos.length > 0 && (
            <ul className="inf-cards" aria-label="Nuevos sin revisar">
              {nuevos.map((path) => {
                const atom = byPath.get(path);
                return (
                  <li key={path} className="inf-card inf-card--new">
                    <div className="inf-card__head">
                      <span className="inf-kind">{atom ? KIND_LABEL[atom.kind] ?? atom.kind : "?"}</span>
                      <span className="inf-tag inf-tag--new">Nuevo, sin revisar</span>
                    </div>
                    <p className="inf-card__text">{atom?.text ?? path}</p>
                    <div className="inf-card__actions">
                      <button type="button" className="btn btn--primary" disabled={busy} onClick={() => void decideNuevo(path, acceptAtom)}>
                        Aceptar
                      </button>
                      <button type="button" className="btn" disabled={busy} onClick={() => void decideNuevo(path, excludeAtom)}>
                        Excluir
                      </button>
                      {atom && (
                        <a className="link-btn" href={textHref(atom)}>
                          Origen
                        </a>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <h4>Átomos del slot ({slot.atomos.length})</h4>
          {slot.atomos.length === 0 ? <p className="inf-help">Este slot todavía no tiene átomos.</p> : <ul className="inf-cards">{slot.atomos.map((p) => renderAtomCard(p, "lista"))}</ul>}
          {slot.excluidos.length > 0 && (
            <>
              <h4>Excluidos a mano ({slot.excluidos.length})</h4>
              <ul className="inf-cards">{slot.excluidos.map((p) => renderAtomCard(p, "excluido"))}</ul>
            </>
          )}
        </section>

        <aside className="inf-col inf-doc" aria-label="Documento final">
          <h3>Documento final</h3>
          <p className="inf-help">{MODE_HELP}</p>
          {preview.map((section) => (
            <PreviewBlock key={section.slot} section={section} onOpen={openItem} />
          ))}
          {provenance && (
            <div className="inf-prov" role="dialog" aria-label="Procedencia">
              <div className="inf-prov__head">
                <strong>
                  Viene de {provenance.atoms.length} {provenance.atoms.length === 1 ? "átomo" : "átomos"}
                </strong>
                <button type="button" className="btn btn--quiet" aria-label="Cerrar procedencia" onClick={() => setProvenance(null)}>
                  ✕
                </button>
              </div>
              <ul>
                {provenance.atoms.map((a) => (
                  <li key={a.id}>
                    <p>{a.text}</p>
                    <blockquote>{a.quote || "Sin cita de ancla."}</blockquote>
                    <a className="link-btn" href={textHref(a)}>
                      Abrir en el texto
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function PreviewBlock({ section, onOpen }: { section: PreviewSection; onOpen(item: PreviewItem): void }) {
  const open = (item: PreviewItem) => (
    <button type="button" className="inf-piece" onClick={() => onOpen(item)}>
      {item.text}
    </button>
  );
  return (
    <section className="inf-sec">
      <h4>{section.label}</h4>
      {section.empty ? (
        <p className="inf-help">Este slot todavía no tiene átomos.</p>
      ) : section.modo === "viñetas" ? (
        <ul>
          {section.items.map((i) => (
            <li key={i.key}>{open(i)}</li>
          ))}
        </ul>
      ) : section.modo === "prosa" ? (
        <>
          <p className="inf-prose">
            {section.items.map((i) => (
              <span key={i.key}>{open(i)} </span>
            ))}
          </p>
          <p className="inf-help">Vista previa unida, no redactada por un modelo.</p>
        </>
      ) : (
        <table className="inf-table">
          <thead>
            <tr>
              <th>Tipo</th>
              <th>Texto</th>
              <th>Relación</th>
            </tr>
          </thead>
          <tbody>
            {section.items.map((i) => (
              <tr key={i.key}>
                <td>{KIND_LABEL[i.kind] ?? i.kind}</td>
                <td>{open(i)}</td>
                <td>{i.relation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
