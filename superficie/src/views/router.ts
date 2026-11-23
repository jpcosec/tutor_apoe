/** Rutas por hash: #/lector, #/destilacion, #/doc/<id>, #/doc/<id>/compose, #/extract, #/salud, #/bandeja,
 * #/atomos/texto/<actaId>[?atom=<id>], #/atomos/grafo[?atom=<id>], #/atomos/informe/<id>. */
import { useEffect, useState } from "react";

export type Route =
  | { view: "home" }
  | { view: "doc"; id: string; mode: "document" | "compose" }
  | { view: "lector" }
  | { view: "destilacion" }
  | { view: "extract" }
  | { view: "salud" }
  | { view: "bandeja" }
  | { view: "atomos-texto"; id: string; focus?: string }
  | { view: "atomos-grafo"; focus?: string }
  | { view: "atomos-informe"; id: string };

const atomQuery = (focus?: string) => (focus ? `?atom=${encodeURIComponent(focus)}` : "");

export function parseRoute(hash: string): Route {
  const [path = "", query = ""] = hash.replace(/^#\/?/, "").split("?");
  const parts = path.split("/").map(decodeURIComponent);
  const focus = new URLSearchParams(query).get("atom") ?? undefined;
  if (parts[0] === "doc" && parts[1]) return { view: "doc", id: parts[1], mode: parts[2] === "compose" ? "compose" : "document" };
  if (parts[0] === "lector") return { view: "lector" };
  if (parts[0] === "destilacion") return { view: "destilacion" };
  if (parts[0] === "extract") return { view: "extract" };
  if (parts[0] === "salud") return { view: "salud" };
  if (parts[0] === "bandeja") return { view: "bandeja" };
  if (parts[0] === "atomos") {
    if (parts[1] === "texto" && parts[2]) return { view: "atomos-texto", id: parts[2], ...(focus && { focus }) };
    if (parts[1] === "grafo") return { view: "atomos-grafo", ...(focus && { focus }) };
    if (parts[1] === "informe" && parts[2]) return { view: "atomos-informe", id: parts[2] };
  }
  return { view: "home" };
}

export function hrefFor(route: Route): string {
  if (route.view === "doc") return `#/doc/${encodeURIComponent(route.id)}${route.mode === "compose" ? "/compose" : ""}`;
  if (route.view === "lector") return "#/lector";
  if (route.view === "destilacion") return "#/destilacion";
  if (route.view === "extract") return "#/extract";
  if (route.view === "salud") return "#/salud";
  if (route.view === "bandeja") return "#/bandeja";
  if (route.view === "atomos-texto") return `#/atomos/texto/${encodeURIComponent(route.id)}${atomQuery(route.focus)}`;
  if (route.view === "atomos-grafo") return `#/atomos/grafo${atomQuery(route.focus)}`;
  if (route.view === "atomos-informe") return `#/atomos/informe/${encodeURIComponent(route.id)}`;
  return "#/";
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export function navigate(route: Route): void {
  window.location.hash = hrefFor(route);
}
