/**
 * Salud del store, de dos fuentes que no hay que confundir:
 *
 * - SERVIDO por SLDB: `/lint`, `/graph/isolated`, `/graph/cycles`. Se muestran tal
 *   cual; si la ruta no responde se dice que no está disponible, no se deriva a mano.
 * - DERIVADO acá: ruido estructural y `canonical:false`, sondeando `/document/segments`.
 *
 * El hallazgo derivado principal es ruido estructural: headings dentro del valor de un
 * field son secciones que el modelo no declara. No es corrupción del documento.
 */
import { useEffect, useState } from "react";
import type { DocumentFinding, GraphNodeRef, HealthReport, LintProblem, StoresCheck, StructuralNoiseFinding } from "../core/contract";
import { collectHealth, storeDivergences } from "../core/health";
import { useDocuments, useSchema, useSldb } from "../react/context";
import { hrefFor } from "./router";

/** Un nodo del grafo: enlaza si es documento, texto plano si es field. */
function NodeLink({ node }: { node: GraphNodeRef }) {
  if (!node.doc) return <span className="health-node health-node--field">{node.label}</span>;
  return (
    <a className="health-node" href={hrefFor({ view: "doc", id: node.doc, mode: "document" })} title={node.uri}>
      {node.label}
    </a>
  );
}

export function HealthView() {
  const { client } = useSldb();
  const [documents, reloadDocuments] = useDocuments();
  const schema = useSchema();
  const [report, setReport] = useState<HealthReport | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);

  const docs = documents.status === "ready" ? documents.data : null;
  const schemaErrors = schema.status === "ready" ? schema.data.errors : null;

  useEffect(() => {
    if (!docs || !schemaErrors) return;
    let alive = true;
    setReport(null);
    setProblem(null);
    setProgress({ done: 0, total: docs.length });
    collectHealth(client, docs, schemaErrors, (done, total) => alive && setProgress({ done, total }))
      .then((result) => alive && setReport(result))
      .catch((error: Error) => alive && setProblem(error.message));
    return () => {
      alive = false;
    };
  }, [client, docs, schemaErrors, attempt]);

  const loading = documents.status === "loading" || schema.status === "loading";
  const loadError = documents.status === "error" ? documents.error : schema.status === "error" ? schema.error : null;
  const retry = () => {
    if (documents.status === "error") reloadDocuments();
    setAttempt((a) => a + 1);
  };

  return (
    <div className="health-view">
      <header className="doc-header">
        <div className="doc-header__id">
          <span className="doc-header__model">Salud del store</span>
          <span className="doc-header__path">Derivado de /graph, /schema y /document/segments</span>
        </div>
        {report && (
          <button type="button" className="link-btn" onClick={retry}>
            Revisar de nuevo
          </button>
        )}
      </header>
      <div className="doc-body">
        <main className="page">
          {loading && <p className="sidebar__note">Revisando documentos…</p>}
          {loadError && (
            <div className="banner banner--error" role="alert">
              No se pudo revisar el store: {loadError}.{" "}
              <button type="button" className="link-btn" onClick={retry}>
                Reintentar
              </button>
            </div>
          )}
          {problem && (
            <div className="banner banner--error" role="alert">
              No se pudo completar la revisión: {problem}.{" "}
              <button type="button" className="link-btn" onClick={retry}>
                Reintentar
              </button>
            </div>
          )}
          {docs && schemaErrors && !report && !problem && (
            <p className="sidebar__note">
              Sondeando segmentos…{" "}
              {progress && (
                <span className="health-progress">
                  {progress.done} de {progress.total}
                </span>
              )}
            </p>
          )}
          {report && (
            <>
              <p className="health-summary">
                {report.checked} {report.checked === 1 ? "documento revisado" : "documentos revisados"}.
              </p>
              <LintSection problems={report.lint} />
              <CyclesSection cycles={report.cycles} />
              <IsolatedSection nodes={report.isolated} />
              <IntegritySection check={report.storeCheck} />
              <StructuralSection findings={report.structural} unreadable={report.unreadable} />
              <FindingSection
                title="Documentos no canónicos"
                empty="Todos los archivos en disco coinciden con el render de su payload."
                findings={report.noncanonical}
              />
              <section className="health-section" aria-label="Modelos que no cargan">
                <h2 className="panel-title">Modelos que no cargan</h2>
                {report.modelErrors.length === 0 ? (
                  <p className="inspector__note">El schema cargó todos sus modelos sin errores.</p>
                ) : (
                  <ul className="health-list">
                    {report.modelErrors.map((model) => (
                      <li key={model.model} className="health-item">
                        <span className="health-item__doc">{model.model}</span>
                        <span className="health-item__detail">{model.error}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </>
          )}
        </main>
        <aside className="inspector">
          <p className="inspector__note">
            <strong>Servido por SLDB:</strong> lint, ciclos y nodos aislados salen de <code>/lint</code>, <code>/graph/cycles</code> y{" "}
            <code>/graph/isolated</code>. No se derivan acá.
          </p>
          <p className="inspector__note">
            <strong>Derivado en el cliente:</strong> ruido estructural y documentos no canónicos, sondeando <code>/document/segments</code> uno por uno.
          </p>
          <p className="inspector__note">
            <strong>Integridad:</strong> la divergencia entre modelo y archivo en disco sale de <code>/stores/check</code>, que trae a todos los
            documentos; <code>canonical:false</code> es solo la parte derivable.
          </p>
        </aside>
      </div>
    </div>
  );
}

/** Cabecera común: título + conteo, y el caso "la ruta no respondió" dicho tal cual. */
function ServedSection({
  title,
  help,
  count,
  unavailable,
  empty,
  children,
}: {
  title: string;
  help: string;
  count: number | null;
  unavailable: boolean;
  empty: string;
  children?: React.ReactNode;
}) {
  return (
    <section className="health-section" aria-label={title}>
      <h2 className="panel-title">
        {title} {!unavailable && count !== null && count > 0 && <span className="sidebar__count">{count}</span>}
      </h2>
      <p className="health-help">{help}</p>
      {unavailable ? (
        <p className="inspector__note">Este análisis no está disponible: el backend no respondió la ruta.</p>
      ) : count === 0 ? (
        <p className="inspector__note">{empty}</p>
      ) : (
        children
      )}
    </section>
  );
}

function LintSection({ problems }: { problems: LintProblem[] | null }) {
  return (
    <ServedSection
      title="Lint del store"
      help="Lo que SLDB reporta en GET /lint. Cada problema trae su tipo y severidad tal como los nombra el backend."
      count={problems?.length ?? null}
      unavailable={problems === null}
      empty="SLDB no reporta problemas de lint."
    >
      <ul className="health-list">
        {problems?.map((problem, index) => (
          <li key={`${problem.doc}-${problem.kind}-${index}`} className="health-item">
            <span className="health-item__doc">{problem.doc}</span>
            <span className="health-item__model">{problem.kind}</span>
            <span className={`health-item__detail${problem.severity === "error" ? " health-item__detail--warn" : ""}`}>{problem.detail}</span>
          </li>
        ))}
      </ul>
    </ServedSection>
  );
}

const DIVERGENCE_LABEL = {
  raiz: "raíz del store",
  contrato: "contrato",
  roster: "lista de documentos",
  "archivo-borrado": "archivo borrado",
  contenido: "editado fuera de SLDB",
  campos: "campos distintos",
} as const;

function IntegritySection({ check }: { check: StoresCheck | null }) {
  const divergences = check ? storeDivergences(check) : [];
  return (
    <ServedSection
      title="Integridad del store"
      help="Lo que SLDB reporta en GET /stores/check: divergencia entre lo indexado y el archivo en disco, documento por documento."
      count={check ? divergences.length : null}
      unavailable={check === null}
      empty={check ? check.summary : ""}
    >
      <ul className="health-list">
        {divergences.map((d, index) => (
          <li key={`${d.model ?? ""}-${d.doc ?? ""}-${d.kind}-${index}`} className="health-item">
            {d.doc ? <a className="health-item__doc" href={hrefFor({ view: "doc", id: d.doc, mode: "document" })}>{d.doc}</a> : <span className="health-item__doc">{d.model ?? "store"}</span>}
            <span className="health-item__model">{DIVERGENCE_LABEL[d.kind]}</span>
            <span className="health-item__detail health-item__detail--warn">{d.detail}</span>
          </li>
        ))}
      </ul>
    </ServedSection>
  );
}

function CyclesSection({ cycles }: { cycles: GraphNodeRef[][] | null }) {
  return (
    <ServedSection
      title="Ciclos"
      help="Caminos cerrados en el grafo, según GET /graph/cycles. Un ciclo no es necesariamente un error, pero sí algo que conviene mirar."
      count={cycles?.length ?? null}
      unavailable={cycles === null}
      empty="El grafo no tiene ciclos."
    >
      <ul className="health-list">
        {cycles?.map((cycle, index) => (
          <li key={index} className="health-item">
            <span className="health-cycle">
              {cycle.map((node, position) => (
                <span key={node.uri}>
                  {position > 0 && <span className="health-cycle__arrow"> → </span>}
                  <NodeLink node={node} />
                </span>
              ))}
            </span>
          </li>
        ))}
      </ul>
    </ServedSection>
  );
}

function IsolatedSection({ nodes }: { nodes: GraphNodeRef[] | null }) {
  return (
    <ServedSection
      title="Documentos aislados"
      help="Documentos sin ninguna arista, según GET /graph/isolated. Se omiten los nodos de tipo field: un campo declarado que nadie referencia todavía es normal."
      count={nodes?.length ?? null}
      unavailable={nodes === null}
      empty="Todos los documentos están conectados al grafo."
    >
      <ul className="health-list">
        {nodes?.map((node) => (
          <li key={node.uri} className="health-item">
            <NodeLink node={node} />
            {node.model && <span className="health-item__model">{node.model}</span>}
          </li>
        ))}
      </ul>
    </ServedSection>
  );
}

function StructuralSection({ findings, unreadable }: { findings: StructuralNoiseFinding[]; unreadable: DocumentFinding[] }) {
  return (
    <section className="health-section" aria-label="Ruido estructural">
      <h2 className="panel-title">
        Ruido estructural {findings.length > 0 && <span className="sidebar__count">{findings.length}</span>}
      </h2>
      <p className="health-help">
        Un <code>#</code> dentro del valor de un field es una sección que el modelo no declara. No es corrupción ni error del documento: extrae y
        renderiza bien, pero pierde su sección. Es un contrato incompleto: la salida es crear un modelo que herede del actual y declare esas
        secciones como campos <code>optrev</code>. SLDB ya rechaza esto al trackear (<code>docs track</code> / <code>docs create</code>); esta vista
        sirve para los documentos que entraron antes de ese cambio.
      </p>
      {findings.length === 0 ? (
        <p className="inspector__note">Ningún documento tiene headings sin declarar dentro de sus fields.</p>
      ) : (
        <ul className="health-list">
          {findings.map((finding) => (
            <li key={finding.doc} className="health-item health-item--heads">
              <a className="health-item__doc" href={hrefFor({ view: "doc", id: finding.doc, mode: "document" })} title={finding.path}>
                {finding.doc}
              </a>
              <span className="health-item__model">{finding.model}</span>
              <span className="health-item__detail health-item__detail--warn">
                {finding.headings.length} {finding.headings.length === 1 ? "sección sin declarar" : "secciones sin declarar"}
              </span>
              <ul className="health-heads">
                {finding.headings.map((heading, index) => (
                  <li key={`${heading}-${index}`}>{heading}</li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
      {unreadable.length > 0 && (
        <div className="health-unreadable">
          <h3 className="panel-subtitle">{unreadable.length} sin lectura</h3>
          <p className="inspector__note">De estos documentos no se pudo derivar nada: `/document/segments` no respondió. No se cuentan como ruido.</p>
          <ul className="health-list">
            {unreadable.map((finding) => (
              <li key={finding.doc} className="health-item">
                <a className="health-item__doc" href={hrefFor({ view: "doc", id: finding.doc, mode: "document" })} title={finding.path}>
                  {finding.doc}
                </a>
                <span className="health-item__model">{finding.model}</span>
                <span className="health-item__detail">{finding.detail}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function FindingSection({ title, empty, findings }: { title: string; empty: string; findings: DocumentFinding[] }) {
  return (
    <section className="health-section" aria-label={title}>
      <h2 className="panel-title">
        {title} {findings.length > 0 && <span className="sidebar__count">{findings.length}</span>}
      </h2>
      {findings.length === 0 ? (
        <p className="inspector__note">{empty}</p>
      ) : (
        <ul className="health-list">
          {findings.map((finding) => (
            <li key={finding.doc} className="health-item">
              <a className="health-item__doc" href={hrefFor({ view: "doc", id: finding.doc, mode: "document" })} title={finding.path}>
                {finding.doc}
              </a>
              <span className="health-item__model">{finding.model}</span>
              <span className="health-item__detail">{finding.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
