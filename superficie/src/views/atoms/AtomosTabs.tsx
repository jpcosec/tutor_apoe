/**
 * Barra de las tres vistas de átomos, como en la maqueta: Extracción · Grafo · Compositor,
 * con el documento de trabajo a la izquierda. Lleva el átomo enfocado de una vista a otra.
 */
import { hrefFor, type Route } from "../router";
import { useAtomStore } from "./useAtomStore";
import "./atomos-tabs.css";

type AtomRoute = Extract<Route, { view: "atomos-texto" | "atomos-grafo" | "atomos-informe" }>;

const TABS = [
  { view: "atomos-texto", label: "Extracción" },
  { view: "atomos-grafo", label: "Grafo" },
  { view: "atomos-informe", label: "Compositor" },
] as const;

export function AtomosTabs({ route }: { route: AtomRoute }) {
  const { actas, informes } = useAtomStore();
  const acta = route.view === "atomos-texto" ? actas.find((a) => a.id === route.id) ?? actas[0] : actas[0];
  const informe = route.view === "atomos-informe" ? route.id : informes[0]?.id;
  const focus = route.view === "atomos-informe" ? undefined : route.focus;
  const hrefs = {
    "atomos-texto": acta ? hrefFor({ view: "atomos-texto", id: acta.id, focus }) : null,
    "atomos-grafo": hrefFor({ view: "atomos-grafo", focus }),
    "atomos-informe": informe ? hrefFor({ view: "atomos-informe", id: informe }) : null,
  } as const;
  return (
    <header className="at-tabs">
      <span className="at-tabs__crumb"><strong>sldb</strong> / {acta ? acta.path : "…"}</span>
      <nav className="at-tabs__nav" aria-label="Vistas de átomos">
        {TABS.map((t) => {
          const href = hrefs[t.view];
          const current = route.view === t.view;
          return href ? (
            <a key={t.view} href={href} className={`at-tabs__tab${current ? " is-current" : ""}`} aria-current={current ? "page" : undefined}>{t.label}</a>
          ) : (
            <span key={t.view} className="at-tabs__tab is-off" title="No hay documento para esta vista">{t.label}</span>
          );
        })}
      </nav>
    </header>
  );
}
