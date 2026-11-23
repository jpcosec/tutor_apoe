/**
 * LECTOR · anclar sobre texto crudo (§6.1, §16).
 *
 * No hay fuentes en el store: el texto crudo lo pega el usuario. Lo que se guarda
 * son anchors sobre ese texto, por `POST /save` en modo `create`.
 *
 * El modelo y sus campos salen del schema en runtime (`/schema`). Este store registra
 * `pron.models:AnchorDoc` (`symbol`, `forms`, `ref`, `steps`, `motive`); otro store
 * puede registrar `sldb.models.anchor_doc` con `kind`/`tags`/`provenance`. El formulario
 * y el payload se derivan de lo declarado, así que las dos variantes funcionan y nunca
 * se manda un campo que el modelo no declara.
 *
 * `DuplicateWarning` (§6.1): con una selección de largo suficiente se consulta
 * `GET /corpus/rank?fields=1` (contra campos, no documentos; con debounce, descartando respuestas viejas) y se muestran los
 * parecidos con su puntaje. Los tres estados se ven distinto: ok (con lista o "es nuevo"),
 * not_indexed (botón "Indexar ahora") y unavailable (con la razón). Es informativo: nunca
 * bloquea ni altera el guardado, y sin respuesta NO se inventa ninguna heurística.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FieldRankHit, SchemaField, SimilarityResult } from "../core/contract";
import {
  anchorIdFor,
  buildPayload,
  classifyHits,
  DUPLICATE_DEBOUNCE_MS,
  duplicateQuery,
  duplicateRankParams,
  scorePercent,
  DOCUMENT_ID,
  draftFromSelection,
  findAnchorModel,
  inputForField,
  lineLabel,
  selectionAt,
  shortenQuote,
  splitByAnchors,
  type AnchorSelection,
  type SessionAnchor,
} from "../core/anchors";
import { SldbHttpError } from "../core/client";
import { useSchema, useSldb } from "../react/context";
import { fieldLabel } from "../core/similarity";
import { hrefFor } from "./router";
import "./reader-similarity.css";

type AnchorSaveState =
  | { status: "idle" }
  | { status: "saving" }
  | { status: "error"; message: string }
  | { status: "saved"; id: string };

type DuplicateLookup =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "indexing" }
  | { status: "done"; result: SimilarityResult<FieldRankHit> };

/** Consulta parecidos de `quote`; una respuesta de una consulta anterior se descarta. */
function useDuplicateLookup(quote: string | null) {
  const { client } = useSldb();
  const query = duplicateQuery(quote);
  const [lookup, setLookup] = useState<DuplicateLookup>({ status: "idle" });
  const latest = useRef<string | null>(null);

  const run = useCallback(
    async (q: string, refresh: boolean) => {
      latest.current = q;
      setLookup({ status: refresh ? "indexing" : "loading" });
      let result: SimilarityResult<FieldRankHit>;
      try {
        result = await client.rank(duplicateRankParams(q, refresh));
      } catch (error) {
        result = { status: "unavailable", reason: error instanceof Error ? error.message : String(error) };
      }
      if (latest.current !== q) return;
      setLookup({ status: "done", result });
    },
    [client],
  );

  useEffect(() => {
    latest.current = query;
    if (!query) {
      setLookup({ status: "idle" });
      return;
    }
    setLookup({ status: "loading" });
    const timer = setTimeout(() => void run(query, false), DUPLICATE_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query, run]);

  const indexNow = useCallback(() => {
    if (query) void run(query, true);
  }, [query, run]);

  return { lookup, query, indexNow };
}

function DuplicateWarning({ lookup, tooShort, indexNow }: { lookup: DuplicateLookup; tooShort: boolean; indexNow(): void }) {
  if (lookup.status === "idle") {
    return tooShort ? <p className="dup-note">Seleccioná un tramo más largo para buscar parecidos.</p> : null;
  }
  if (lookup.status === "loading") return <p className="dup-note" role="status">Buscando parecidos…</p>;
  if (lookup.status === "indexing") return <p className="dup-note" role="status">Indexando el corpus…</p>;
  const { result } = lookup;
  if (result.status === "unavailable") {
    return (
      <p className="dup-box dup-box--unavailable" role="status">
        Similitud no disponible: {result.reason}.
      </p>
    );
  }
  if (result.status === "not_indexed") {
    return (
      <div className="dup-box dup-box--not-indexed" role="status">
        <p>El corpus todavía no está indexado: no se puede saber si esto ya existe.</p>
        <button type="button" className="btn" onClick={indexNow}>
          Indexar ahora
        </button>
      </div>
    );
  }
  const { duplicates, similar } = classifyHits(result.hits);
  if (duplicates.length + similar.length === 0) {
    return (
      <p className="dup-box dup-box--new" role="status">
        No hay nada parecido: es nuevo.
      </p>
    );
  }
  return (
    <div className="dup-box" role="status" aria-label="Parecidos">
      <ul className="dup-list">
        {[...duplicates, ...similar].map((hit) => {
          const isDuplicate = duplicates.includes(hit);
          return (
            <li key={hit.id} className={isDuplicate ? "dup-hit dup-hit--duplicate" : "dup-hit"}>
              {isDuplicate && <strong className="dup-hit__flag">Posible duplicado ({scorePercent(hit.score)}%)</strong>}
              <a href={hrefFor({ view: "doc", id: hit.name, mode: "document" })}>{fieldLabel(hit)}</a>
              {!isDuplicate && <span className="dup-hit__score">{scorePercent(hit.score)}%</span>}
            </li>
          );
        })}
      </ul>
      <p className="dup-note">Parecido de texto, no de significado. Es solo un aviso: podés guardar igual.</p>
    </div>
  );
}

export function ReaderView() {
  const { client } = useSldb();
  const schema = useSchema();
  const models = schema.status === "ready" ? schema.data.models : [];
  const model = useMemo(() => findAnchorModel(models), [models]);
  const [text, setText] = useState("");
  const [selection, setSelection] = useState<AnchorSelection | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [save, setSave] = useState<AnchorSaveState>({ status: "idle" });
  const [anchors, setAnchors] = useState<SessionAnchor[]>([]);
  const { lookup, query: dupQuery, indexNow } = useDuplicateLookup(selection?.quote ?? null);

  // Una selección nueva arma el formulario desde cero: símbolo sugerido, resto vacío.
  useEffect(() => {
    setDraft(selection && model ? draftFromSelection(model, selection) : {});
    setSave((state) => (state.status === "saved" ? { status: "idle" } : state));
  }, [selection, model]);

  const readSelection = (element: HTMLTextAreaElement) => {
    setSelection(selectionAt(element.value, element.selectionStart, element.selectionEnd));
  };

  const setField = (name: string, value: string) => setDraft((current) => ({ ...current, [name]: value }));

  const preview = useMemo(() => (model && selection ? buildPayload(draft, model) : null), [draft, model, selection]);
  const ready = save.status !== "saving";
  const symbolValue = preview && preview.errors.length === 0 ? String(preview.payload.symbol ?? draft.symbol ?? "") : (draft.symbol ?? "");
  const id = anchorIdFor(symbolValue);
  const canSave = Boolean(model && selection && preview && preview.errors.length === 0 && DOCUMENT_ID.test(id) && ready);

  const create = async () => {
    if (!model || !selection || !preview || preview.errors.length > 0) return;
    setSave({ status: "saving" });
    try {
      await client.save([{ id, action: "create", model: model.id, payload: preview.payload }]);
      setAnchors((current) => [
        ...current,
        {
          id,
          symbol: symbolValue,
          quote: selection.quote,
          start: selection.start,
          end: selection.end,
          startLine: selection.startLine,
          endLine: selection.endLine,
        },
      ]);
      setSave({ status: "saved", id });
    } catch (error) {
      // El mensaje del backend se muestra tal cual: es el que dice qué rechazó.
      setSave({ status: "error", message: error instanceof SldbHttpError ? error.message : String(error) });
    }
  };

  const schemaError = schema.status === "error" ? schema.error : null;
  const runs = useMemo(() => splitByAnchors(text, anchors), [text, anchors]);

  return (
    <div className="reader-view">
      <header className="doc-header">
        <div className="doc-header__id">
          <span className="doc-header__model">Lector</span>
          <span className="doc-header__path">Texto crudo → anchors</span>
        </div>
        {anchors.length > 0 && (
          <span className="save-status">
            {anchors.length} {anchors.length === 1 ? "anchor creado" : "anchors creados"}
          </span>
        )}
      </header>
      <div className="doc-body">
        <main className="reader-page">
          <label className="reader-source-label">
            Texto crudo
            <textarea
              className="reader-input"
              aria-label="Texto crudo"
              placeholder="Pega aquí el correo, el acta o el .md. Después seleccioná un tramo para anclarlo."
              value={text}
              onChange={(event) => setText(event.target.value)}
              onSelect={(event) => readSelection(event.currentTarget)}
            />
          </label>
          <p className="inspector__note">
            El texto no vive en el store: se pega acá y solo se guardan los anchors que declares sobre él. La cita y las líneas quedan como
            procedencia.
          </p>
          {schemaError && (
            <div className="banner banner--error" role="alert">
              No se pudo leer el schema del store: {schemaError}.
            </div>
          )}
          {schema.status === "ready" && !model && (
            <div className="banner" role="alert">
              El store no registra un modelo de anchors: no hay <code>AnchorDoc</code> ni una variante que se le parezca en <code>/schema</code>.
            </div>
          )}
          {anchors.length > 0 && (
            <section className="reader-marked" aria-label="Texto con tramos anclados">
              <h2 className="panel-title">Texto con tramos anclados</h2>
              <pre className="reader-source">
                {runs.map((run, index) =>
                  run.anchor ? (
                    <mark key={`${run.anchor.id}-${index}`} className="reader-mark" title={run.anchor.id}>
                      {run.text}
                    </mark>
                  ) : (
                    <span key={index}>{run.text}</span>
                  ),
                )}
              </pre>
            </section>
          )}
        </main>
        <aside className="inspector reader-panel">
          <section aria-label="Selección">
            <h3 className="panel-subtitle">Selección</h3>
            {selection ? (
              <>
                <blockquote className="reader-quote">{selection.quote}</blockquote>
                <p className="reader-lines">{lineLabel(selection)}</p>
              </>
            ) : (
              <p className="inspector__note">Seleccioná un tramo del texto para anclarlo.</p>
            )}
            {selection && <DuplicateWarning lookup={lookup} tooShort={!dupQuery} indexNow={indexNow} />}
          </section>

          {model && selection && (
            <section className="reader-form" aria-label={`Anchor ${model.id}`}>
              <h3 className="panel-subtitle">Anchor {model.id}</h3>
              {model.fields.map((field) => (
                <FieldInput
                  key={field.name}
                  field={field}
                  value={draft[field.name] ?? ""}
                  disabled={!ready}
                  onChange={(value) => setField(field.name, value)}
                />
              ))}
              <p className="reader-id">
                id: <strong>{id}</strong>
              </p>
              {preview && preview.errors.length > 0 && (
                <ul className="reader-errors" role="alert">
                  {preview.errors.map((error) => (
                    <li key={error.field} className="field-error">
                      {error.message}
                    </li>
                  ))}
                </ul>
              )}
              {preview && preview.errors.length === 0 && (
                <pre className="reader-preview" aria-label="Payload que se va a guardar">
                  {JSON.stringify(preview.payload, null, 2)}
                </pre>
              )}
              <button type="button" className="btn btn--primary" disabled={!canSave} onClick={() => void create()}>
                {save.status === "saving" ? "Guardando…" : "Guardar anchor"}
              </button>
              {save.status === "saved" && (
                <div className="banner banner--ok" role="status">
                  Guardado <strong>{save.id}</strong>.{" "}
                  <a href={hrefFor({ view: "doc", id: save.id, mode: "document" })}>Abrir documento</a>
                </div>
              )}
              {save.status === "error" && (
                <div className="banner banner--error" role="alert">
                  {save.message}
                </div>
              )}
            </section>
          )}

          {anchors.length > 0 && (
            <section aria-label="Anchors de esta sesión">
              <h3 className="panel-subtitle">Anchors de esta sesión</h3>
              <ul className="reader-anchors">
                {anchors.map((anchor) => (
                  <li key={anchor.id} className="reader-anchor">
                    <a className="reader-anchor__id" href={hrefFor({ view: "doc", id: anchor.id, mode: "document" })}>
                      {anchor.id}
                    </a>
                    <span className="reader-anchor__meta">
                      {anchor.symbol} · {lineLabel(anchor)}
                    </span>
                    <p className="reader-anchor__quote">{shortenQuote(anchor.quote)}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}

/** Un campo declarado por el modelo, editado según su kind. */
function FieldInput({
  field,
  value,
  disabled,
  onChange,
}: {
  field: SchemaField;
  value: string;
  disabled: boolean;
  onChange(value: string): void;
}) {
  const input = inputForField(field);
  const id = `anchor-field-${field.name}`;
  const label = (
    <>
      {field.name}
      {field.required ? " *" : ""}
    </>
  );

  if (input === "boolean") {
    return (
      <label className="reader-field" htmlFor={id} title={field.description}>
        <span className="reader-field__label">{label}</span>
        <input id={id} type="checkbox" checked={value === "true"} disabled={disabled} onChange={(event) => onChange(event.target.checked ? "true" : "false")} />
      </label>
    );
  }
  if (input === "select") {
    return (
      <label className="reader-field" htmlFor={id} title={field.description}>
        <span className="reader-field__label">{label}</span>
        <select id={id} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
          <option value="">Elige…</option>
          {field.enum?.map((option) => (
            <option key={String(option)} value={String(option)}>
              {String(option)}
            </option>
          ))}
        </select>
      </label>
    );
  }
  if (input === "textarea") {
    return (
      <label className="reader-field" htmlFor={id} title={field.description}>
        <span className="reader-field__label">{label}</span>
        <textarea id={id} rows={5} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} />
      </label>
    );
  }
  if (input === "json") {
    return (
      <label className="reader-field" htmlFor={id} title={field.description}>
        <span className="reader-field__label">{label}</span>
        <textarea
          id={id}
          rows={3}
          spellCheck={false}
          value={value}
          disabled={disabled}
          placeholder={field.kind === "stringlist" ? "a, b  ·  o JSON [\"a\",\"b\"]" : "JSON"}
          onChange={(event) => onChange(event.target.value)}
        />
      </label>
    );
  }
  return (
    <label className="reader-field" htmlFor={id} title={field.description}>
      <span className="reader-field__label">{label}</span>
      <input id={id} type={input === "number" ? "number" : "text"} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}
