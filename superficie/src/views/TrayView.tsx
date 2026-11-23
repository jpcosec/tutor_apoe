/**
 * BANDEJA · lo anotado sin ubicar (§6.4).
 *
 * Lista lo que no tiene lugar y sugiere destino por similitud: para cada documento
 * pide a `GET /corpus/rank` los ubicados más parecidos (hasta 3, con su puntaje).
 * Los pedidos van de a uno, sin bloquear la UI, y se guardan en memoria mientras
 * dure la vista. Las sugerencias nunca se aplican solas: la bandeja no mueve nada.
 * Los tres estados de la similitud se ven distinto (sin parecidos / no indexado /
 * no disponible) y jamás se simula un ranking cuando el servidor no responde.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { GraphDocument } from "../core/contract";
import { queryText, SUGGEST_THRESHOLD, similarityNotice } from "../core/similarity";
import {
  collectTray,
  groupByModel,
  pickSuggestions,
  placedIds,
  SUGGESTION_LIMIT,
  trayQuery,
  type Suggestion,
  type TrayEntry,
  type TrayReason,
} from "../core/tray";
import { useDocuments, useSchema, useSldb } from "../react/context";
import "./tray-similarity.css";
import { hrefFor } from "./router";

/** Estado de las sugerencias de UN documento. */
type SuggestState =
  | { status: "loading" }
  | { status: "ok"; suggestions: Suggestion[] }
  | { status: "empty"; why: string }
  | { status: "not_indexed" }
  | { status: "unavailable"; reason: string };

const REASON_LABEL: Record<TrayReason, string> = {
  "sin-procedencia": "sin procedencia",
  "marcado-borrador": "marcado borrador",
};

/**
 * Pide sugerencias de a un documento, en orden, con `refresh:false` (solo lee lo indexado).
 * `not_indexed` y `unavailable` son estados del servicio, no del documento: se detiene la cola
 * y se marcan así los pendientes. `indexNow` construye el índice (lento) y reintenta.
 */
function useSuggestions(docs: GraphDocument[] | null, entries: TrayEntry[]) {
  const { client } = useSldb();
  const [states, setStates] = useState<Record<string, SuggestState>>({});
  const [indexing, setIndexing] = useState(false);
  const cache = useRef(new Map<string, SuggestState>());
  const [round, setRound] = useState(0);
  const refreshNext = useRef(false);

  const byId = useMemo(() => new Map((docs ?? []).map((d) => [d.id, d])), [docs]);
  const among = useMemo(() => (docs ? placedIds(docs, entries) : []), [docs, entries]);
  const amongKey = among.join(",");

  useEffect(() => {
    if (!docs || entries.length === 0) return;
    let cancelled = false;
    const refresh = refreshNext.current;
    refreshNext.current = false;
    const publish = () => !cancelled && setStates(Object.fromEntries(cache.current));

    (async () => {
      const pending = entries.filter((e) => !cache.current.has(e.doc));
      for (const e of pending) cache.current.set(e.doc, { status: "loading" });
      publish();
      let first = true;
      for (let n = 0; n < pending.length; n++) {
        const entry = pending[n]!;
        const doc = byId.get(entry.doc);
        const q = doc ? trayQuery(doc) : "";
        if (!doc || queryText(q) === "") {
          cache.current.set(entry.doc, { status: "empty", why: "el documento no tiene texto que comparar" });
        } else if (among.length === 0) {
          cache.current.set(entry.doc, { status: "empty", why: "no hay documentos ubicados con qué comparar" });
        } else {
          const result = await client.rank({ q, k: SUGGESTION_LIMIT, threshold: SUGGEST_THRESHOLD, among, refresh: refresh && first });
          first = false;
          if (cancelled) return;
          if (result.status === "ok") {
            const suggestions = pickSuggestions(result.hits, entry.doc);
            cache.current.set(entry.doc, suggestions.length ? { status: "ok", suggestions } : { status: "empty", why: "" });
          } else {
            // Estado del servicio: vale para todos los que faltan.
            const state: SuggestState = result.status === "not_indexed" ? { status: "not_indexed" } : { status: "unavailable", reason: result.reason };
            for (const rest of pending.slice(n)) cache.current.set(rest.doc, state);
            publish();
            return;
          }
        }
        publish();
      }
    })();
    return () => {
      cancelled = true;
      // Lo que quedó cargando se reintenta en la próxima corrida.
      for (const [key, value] of cache.current) if (value.status === "loading") cache.current.delete(key);
    };
    // `entries` cambia de identidad solo cuando cambia su contenido (useMemo sobre docs/schema).
  }, [client, docs, entries, byId, amongKey, round]); // eslint-disable-line react-hooks/exhaustive-deps

  const indexNow = useCallback(() => {
    setIndexing(true);
    for (const [key, value] of [...cache.current]) if (value.status === "not_indexed" || value.status === "unavailable") cache.current.delete(key);
    refreshNext.current = true;
    setStates((prev) => Object.fromEntries(Object.entries(prev).map(([k, v]) => [k, v.status === "not_indexed" ? ({ status: "loading" } as SuggestState) : v])));
    setRound((r) => r + 1);
  }, []);

  // Deja de mostrar "indexando" cuando ya no queda ningún documento cargando.
  useEffect(() => {
    if (indexing && !Object.values(states).some((s) => s.status === "loading")) setIndexing(false);
  }, [indexing, states]);

  return { states, indexing, indexNow };
}

export function TrayView() {
  const [documents, reload] = useDocuments();
  const schema = useSchema();
  const [only, setOnly] = useState<TrayReason | "todas">("todas");

  const docs = documents.status === "ready" ? documents.data : null;
  const schemaIndex = schema.status === "ready" ? schema.data : null;

  const entries = useMemo(() => (docs ? collectTray(docs, schemaIndex) : []), [docs, schemaIndex]);
  const filtered = useMemo(() => (only === "todas" ? entries : entries.filter((e) => e.reasons.includes(only))), [entries, only]);
  const groups = useMemo(() => groupByModel(filtered), [filtered]);
  const { states, indexing, indexNow } = useSuggestions(docs, entries);

  const loading = documents.status === "loading" || schema.status === "loading";
  const error = documents.status === "error" ? documents.error : null;

  return (
    <div className="tray-view">
      <header className="doc-header">
        <div className="doc-header__id">
          <span className="doc-header__model">Bandeja</span>
          <span className="doc-header__path">Documentos anotados que todavía no tienen lugar</span>
        </div>
        {docs && (
          <span className="save-status">
            {entries.length} {entries.length === 1 ? "sin ubicar" : "sin ubicar"}
          </span>
        )}
      </header>
      <div className="doc-body">
        <main className="page">
          {loading && <p className="sidebar__note">Leyendo el store…</p>}
          {error && (
            <div className="banner banner--error" role="alert">
              No se pudo leer el store: {error}.{" "}
              <button type="button" className="link-btn" onClick={reload}>
                Reintentar
              </button>
            </div>
          )}
          {docs && (
            <>
              <div className="tray-filters" role="group" aria-label="Filtrar por motivo">
                {(["todas", "sin-procedencia", "marcado-borrador"] as const).map((key) => (
                  <button
                    key={key}
                    type="button"
                    className={`tray-filter${only === key ? " is-active" : ""}`}
                    aria-pressed={only === key}
                    onClick={() => setOnly(key)}
                  >
                    {key === "todas" ? "Todas" : REASON_LABEL[key]}
                    <span className="sidebar__count">
                      {key === "todas" ? entries.length : entries.filter((e) => e.reasons.includes(key)).length}
                    </span>
                  </button>
                ))}
              </div>

              {filtered.length === 0 ? (
                <p className="inspector__note">
                  {entries.length === 0
                    ? "Nada sin ubicar: todos los documentos que declaran procedencia la tienen."
                    : "Ningún documento cae en este motivo."}
                </p>
              ) : (
                groups.map((group) => (
                  <section key={group.model} className="tray-group" aria-label={group.model}>
                    <h2 className="panel-title">
                      {group.model} <span className="sidebar__count">{group.entries.length}</span>
                    </h2>
                    <ul className="tray-list">
                      {group.entries.map((entry) => (
                        <TrayCard key={entry.doc} entry={entry} state={states[entry.doc]} indexing={indexing} onIndex={indexNow} />
                      ))}
                    </ul>
                  </section>
                ))
              )}
            </>
          )}
        </main>
        <aside className="inspector">
          <p className="inspector__note">
            Un documento entra a la bandeja si su modelo declara <code>provenance</code> y lo tiene vacío, o si está tageado como borrador. Si el
            modelo no declara procedencia, el documento no aparece: la regla no le aplica.
          </p>
          <p className="inspector__note">
            <strong>Destino sugerido.</strong> Se compara el texto de cada documento con el de los ya ubicados (los que no están en la bandeja) y se
            muestran hasta {SUGGESTION_LIMIT} con parecido de al menos {Math.round(SUGGEST_THRESHOLD * 100)}%. El puntaje mide parecido de{" "}
            <em>texto</em>, no de significado. Nada se mueve solo.
          </p>
        </aside>
      </div>
    </div>
  );
}

function Suggestions({ state, indexing, onIndex }: { state: SuggestState | undefined; indexing: boolean; onIndex: () => void }) {
  if (!state || state.status === "loading") {
    return (
      <p className="tray-suggest tray-suggest--note" role="status">
        {indexing ? "Indexando el corpus…" : "Buscando parecidos…"}
      </p>
    );
  }
  if (state.status === "ok") {
    return (
      <ul className="tray-suggest tray-suggest__list" aria-label="Destinos sugeridos">
        {state.suggestions.map((s) => (
          <li key={s.name} className="tray-suggest__item">
            <span className="tray-suggest__score" title="Parecido de texto, no de significado">
              {s.percent}%
            </span>
            <a href={hrefFor({ view: "doc", id: s.name, mode: "document" })} title={`${s.model}:${s.name}`}>
              {s.title}
            </a>
          </li>
        ))}
      </ul>
    );
  }
  if (state.status === "empty") {
    return <p className="tray-suggest tray-suggest--note">Sin parecidos{state.why ? `: ${state.why}` : ""}.</p>;
  }
  const notice = similarityNotice(state.status === "not_indexed" ? { status: "not_indexed" } : { status: "unavailable", reason: state.reason });
  return (
    <p className="tray-suggest tray-suggest--warn" role="status">
      {notice}{" "}
      {state.status === "not_indexed" && (
        <button type="button" className="link-btn" onClick={onIndex}>
          Indexar ahora
        </button>
      )}
    </p>
  );
}

function TrayCard({ entry, state, indexing, onIndex }: { entry: TrayEntry; state: SuggestState | undefined; indexing: boolean; onIndex: () => void }) {
  return (
    <li className="tray-card">
      <div className="tray-card__head">
        <a className="tray-card__title" href={hrefFor({ view: "doc", id: entry.doc, mode: "document" })} title={entry.path}>
          {entry.title}
        </a>
        <span className="tray-card__reasons">
          {entry.reasons.map((reason) => (
            <span key={reason} className={`tray-tag tray-tag--${reason}`}>
              {REASON_LABEL[reason]}
            </span>
          ))}
        </span>
      </div>
      {entry.excerpt && <p className="tray-card__excerpt">{entry.excerpt}</p>}
      <span className="tray-card__path">{entry.path}</span>
      <Suggestions state={state} indexing={indexing} onIndex={onIndex} />
    </li>
  );
}
