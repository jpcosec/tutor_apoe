/** Navegación: documentos del store agrupados por modelo, y la entrada a extracción. */
import { useMemo, useState } from "react";
import type { GraphDocument } from "../core/contract";
import { useDocuments } from "../react/context";
import { hrefFor, type Route } from "./router";
import { ThemeToggle } from "./ThemeToggle";

function titleOf(doc: GraphDocument): string {
  const title = doc.payload.title;
  return typeof title === "string" && title.trim() ? title : doc.id;
}

export function Sidebar({ route }: { route: Route }) {
  const [documents, reload] = useDocuments();
  const [query, setQuery] = useState("");
  const groups = useMemo(() => {
    if (documents.status !== "ready") return [];
    const q = query.trim().toLowerCase();
    const byModel = new Map<string, GraphDocument[]>();
    for (const doc of documents.data) {
      if (q && !`${doc.id} ${titleOf(doc)} ${doc.model_name}`.toLowerCase().includes(q)) continue;
      byModel.set(doc.model_name, [...(byModel.get(doc.model_name) ?? []), doc]);
    }
    return [...byModel.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [documents, query]);
  const activeId = route.view === "doc" ? route.id : null;
  const firstActa = documents.status === "ready" ? documents.data.find((d) => d.model_name === "ActaDoc") : undefined;
  const firstInforme = documents.status === "ready" ? documents.data.find((d) => d.model_name === "InformeAvanceDoc") : undefined;

  return (
    <nav className="sidebar" aria-label="Documentos">
      <div className="sidebar__head">
        <div className="sidebar__brand">SLDB</div>
        <ThemeToggle />
      </div>
      <a className={`sidebar__action${route.view === "lector" ? " is-active" : ""}`} href={hrefFor({ view: "lector" })}>
        Lector
      </a>
      <a className={`sidebar__action${route.view === "extract" ? " is-active" : ""}`} href={hrefFor({ view: "extract" })}>
        Extraer desde texto
      </a>
      <a className={`sidebar__action${route.view === "destilacion" ? " is-active" : ""}`} href={hrefFor({ view: "destilacion" })}>
        Destilación
      </a>
      <a className={`sidebar__action${route.view === "bandeja" ? " is-active" : ""}`} href={hrefFor({ view: "bandeja" })}>
        Bandeja
      </a>
      <a className={`sidebar__action${route.view === "salud" ? " is-active" : ""}`} href={hrefFor({ view: "salud" })}>
        Salud del store
      </a>
      <div className="sidebar__note">Átomos</div>
      {firstActa ? (
        <a className={`sidebar__action${route.view === "atomos-texto" ? " is-active" : ""}`} href={hrefFor({ view: "atomos-texto", id: firstActa.id })}>
          Átomos en el texto
        </a>
      ) : (
        <span className="sidebar__note">Átomos en el texto: sin actas</span>
      )}
      <a className={`sidebar__action${route.view === "atomos-grafo" ? " is-active" : ""}`} href={hrefFor({ view: "atomos-grafo" })}>
        Grafo de átomos
      </a>
      {firstInforme ? (
        <a className={`sidebar__action${route.view === "atomos-informe" ? " is-active" : ""}`} href={hrefFor({ view: "atomos-informe", id: firstInforme.id })}>
          Informe
        </a>
      ) : (
        <span className="sidebar__note">Informe: sin informes</span>
      )}
      <input className="sidebar__search" type="search" placeholder="Buscar documento" aria-label="Buscar documento" value={query} onChange={(e) => setQuery(e.target.value)} />
      {documents.status === "loading" && <p className="sidebar__note">Cargando documentos…</p>}
      {documents.status === "error" && (
        <p className="sidebar__note">
          No se pudo leer el store: {documents.error}.{" "}
          <button type="button" className="link-btn" onClick={reload}>
            Reintentar
          </button>
        </p>
      )}
      {groups.map(([model, docs]) => (
        <details key={model} className="sidebar__group" open={docs.length <= 25 || docs.some((d) => d.id === activeId)}>
          <summary>
            {model} <span className="sidebar__count">{docs.length}</span>
          </summary>
          <ul>
            {docs.map((doc) => (
              <li key={doc.id}>
                <a className={doc.id === activeId ? "is-active" : undefined} href={hrefFor({ view: "doc", id: doc.id, mode: "document" })} title={doc.path}>
                  {titleOf(doc)}
                </a>
              </li>
            ))}
          </ul>
        </details>
      ))}
    </nav>
  );
}
