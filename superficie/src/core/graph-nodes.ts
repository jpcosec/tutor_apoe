/**
 * Los endpoints de análisis de SLDB (`/graph/isolated`, `/graph/cycles`) nombran
 * nodos como URI, no como id de documento:
 *
 *   sldb://document/ConversationStep:step-cobranza-respuesta
 *   sldb://field/AgentFraming.framing
 *
 * Solo los nodos `document` son enlazables a una vista: un nodo `field` es una
 * posición del schema, no un documento que se pueda abrir.
 */
import type { GraphNodeRef } from "./contract";

const URI = /^sldb:\/\/([^/]+)\/(.+)$/;

/** Parte una URI de nodo. Si no matchea el esquema, se devuelve cruda y sin `doc`. */
export function parseNode(uri: string): GraphNodeRef {
  const match = URI.exec(uri);
  const kind = match?.[1];
  const rest = match?.[2];
  if (!kind || !rest) return { uri, kind: "unknown", label: uri };
  if (kind === "document") {
    const cut = rest.indexOf(":");
    if (cut < 0) return { uri, kind, label: rest };
    return { uri, kind, model: rest.slice(0, cut), doc: rest.slice(cut + 1), label: rest.slice(cut + 1) };
  }
  const dot = rest.indexOf(".");
  if (kind === "field" && dot > 0) return { uri, kind, model: rest.slice(0, dot), label: rest };
  return { uri, kind, label: rest };
}

export function parseNodes(uris: string[]): GraphNodeRef[] {
  return uris.map(parseNode);
}

/**
 * Los nodos aislados de tipo `field` son ruido para una vista de salud: un campo
 * declarado que ningún documento referencia todavía es normal. Lo accionable son
 * los DOCUMENTOS que quedaron fuera del grafo.
 */
export function isolatedDocuments(uris: string[]): GraphNodeRef[] {
  return parseNodes(uris).filter((node) => node.kind === "document");
}
