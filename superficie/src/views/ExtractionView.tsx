/**
 * Extracción: pega o carga un texto, elige un modelo y ve qué atoms (fields) salen,
 * cuánto del texto queda cubierto y qué partes no caben en el modelo. Si sirve, se
 * guarda como documento nuevo.
 */
import { useMemo, useState } from "react";
import type { ExtractionSegments } from "../core/contract";
import { SaveConflictError, SldbHttpError } from "../core/client";
import { FieldColors } from "../core/colors";
import { useSchema, useSldb } from "../react/context";
import { ExtractionSurface } from "../react/ExtractionSurface";
import { navigate } from "./router";

export function ExtractionView() {
  const { client } = useSldb();
  const schema = useSchema();
  const [model, setModel] = useState("");
  const [text, setText] = useState("");
  const [result, setResult] = useState<ExtractionSegments | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [highlight, setHighlight] = useState<string | null>(null);
  const colors = useMemo(() => new FieldColors(result?.fields.map((f) => FieldColors.keyFor(f.path)) ?? []), [result]);
  const models = schema.status === "ready" ? schema.data.models : [];

  const run = async () => {
    setBusy(true);
    setProblem(null);
    try {
      setResult(await client.extract(model, text));
    } catch (error) {
      setResult(null);
      setProblem((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const loadFile = async (file: File | undefined) => file && setText(await file.text());

  return (
    <div className="extract-view">
      <header className="doc-header">
        <div className="doc-header__id">
          <span className="doc-header__model">Extracción</span>
          <span className="doc-header__path">Texto crudo → fields de un modelo</span>
        </div>
      </header>
      <div className="doc-body">
        <main className="page">
          <div className="extract-form">
            <label>
              Modelo
              <select value={model} onChange={(e) => setModel(e.target.value)}>
                <option value="">Elige un modelo</option>
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.id}
                  </option>
                ))}
              </select>
            </label>
            <label className="extract-form__file">
              Cargar archivo
              <input type="file" accept=".md,.txt,text/*" onChange={(e) => void loadFile(e.target.files?.[0])} />
            </label>
            <textarea aria-label="Texto crudo" placeholder="Pega aquí un correo, un acta o un .md" value={text} onChange={(e) => setText(e.target.value)} rows={result ? 6 : 16} />
            <button type="button" className="btn btn--primary" disabled={!model || !text.trim() || busy} onClick={() => void run()}>
              {busy ? "Detectando…" : "Detectar fields"}
            </button>
          </div>
          {problem && (
            <div className="banner banner--error" role="alert">
              SLDB no pudo extraer con {model}: {problem}
            </div>
          )}
          {result && (
            <>
              <Coverage value={result.coverage} unmatched={result.unmatched.length} />
              <ExtractionSurface result={result} colors={colors} highlight={highlight} />
            </>
          )}
        </main>
        <aside className="inspector">
          {result ? (
            <ExtractedFields result={result} colors={colors} onHighlight={setHighlight} />
          ) : (
            <p className="inspector__note">Los fields detectados aparecen aquí, con su valor tipado.</p>
          )}
          {result && <CreateDocument model={model} result={result} />}
        </aside>
      </div>
    </div>
  );
}

function Coverage({ value, unmatched }: { value: number; unmatched: number }) {
  const percent = Math.round(value * 100);
  return (
    <div className="coverage">
      <div className="coverage__bar" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} aria-label="Texto cubierto por fields">
        <span style={{ width: `${percent}%` }} />
      </div>
      <p>
        {percent}% del texto sale a algún field.{" "}
        {unmatched > 0 ? `${unmatched} ${unmatched === 1 ? "tramo no cabe" : "tramos no caben"} en el modelo (rayado).` : "Nada quedó fuera del modelo."}
      </p>
    </div>
  );
}

function ExtractedFields({ result, colors, onHighlight }: { result: ExtractionSegments; colors: FieldColors; onHighlight(key: string | null): void }) {
  return (
    <section className="legend" aria-label="Fields detectados">
      <h2 className="panel-title">Fields detectados</h2>
      <ul>
        {result.fields.map((field) => {
          const key = FieldColors.keyFor(field.path);
          return (
            <li key={`${field.path}-${field.start}`} className={`legend__row f-${colors.slotOf(key)}`} onMouseEnter={() => onHighlight(key)} onMouseLeave={() => onHighlight(null)}>
              <span className="legend__swatch" aria-hidden />
              <span className="legend__name">{field.path}</span>
              <span className="legend__meta">{field.alignment === "approximate" ? "posición aproximada" : field.kind ?? field.marker}</span>
              <span className="legend__value">{typeof field.value === "string" ? field.value : JSON.stringify(field.value)}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function CreateDocument({ model, result }: { model: string; result: ExtractionSegments }) {
  const { client } = useSldb();
  const [id, setId] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const create = async () => {
    setProblem(null);
    try {
      await client.save([{ id, action: "create", model, payload: result.payload }]);
      navigate({ view: "doc", id, mode: "document" });
    } catch (error) {
      setProblem(error instanceof SaveConflictError || error instanceof SldbHttpError ? error.message : String(error));
    }
  };
  return (
    <section className="create-doc" aria-label="Guardar como documento">
      <h3 className="panel-subtitle">Guardar como documento</h3>
      <input className="add-input" placeholder="id-del-documento" aria-label="Identificador del documento" value={id} onChange={(e) => setId(e.target.value)} />
      <button type="button" className="btn btn--primary" disabled={!/^[a-zA-Z0-9][a-zA-Z0-9_-]*$/.test(id)} onClick={() => void create()}>
        Crear {model}
      </button>
      {problem && <p className="field-error">{problem}</p>}
      <p className="inspector__note">Se guarda el payload extraído; SLDB renderiza el archivo y verifica el round-trip.</p>
    </section>
  );
}
