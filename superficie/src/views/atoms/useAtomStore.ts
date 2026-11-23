/**
 * Store compartido de las vistas de átomos: carga `/graph` y `/edges`, deriva átomos, actas,
 * informes y tipos de relación con las funciones puras de `core/atoms`, y expone las escrituras.
 * Toda escritura va por el cliente (`/save` con `expected`, `POST /docs`) y recarga al terminar.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { actasFromDocuments, atomsFromDocuments, informesFromDocuments, relationTypesFromDocuments } from "../../core/atoms";
import { respuestasFromDocuments, sourcesFromDocuments } from "../../core/caso";
import { groupInfosFromDocuments, type GroupInfo } from "../../core/atom-groups";
import type { Acta, Atom, Fuente, Respuesta, CreateDocumentResult, Edge, GraphDocument, Informe, Payload, RelationTypeSpec, SaveResult } from "../../core/contract";
import { setAt } from "../../core/paths";
import { useSldb } from "../../react/context";

export type AtomStoreStatus = "loading" | "ok" | "error";

export interface AtomStore {
  status: AtomStoreStatus;
  /** Mensaje cuando `status === "error"`; `null` si no. */
  error: string | null;
  atoms: Atom[];
  actas: Acta[];
  /** Fuentes de texto de ambos modelos (`FuenteDoc` y `ActaDoc`) con la misma forma. */
  fuentes: Fuente[];
  /** `GrupoDoc` (título de display de bases y subgrupos). */
  grupos: GroupInfo[];
  /** `RespuestaDoc` del caso. */
  respuestas: Respuesta[];
  /** Informes de cualquier modelo con slots (`InformeAvanceDoc`, `SalidaDoc`…). */
  informes: Informe[];
  relationTypes: RelationTypeSpec[];
  edges: Edge[];
  /** Todos los documentos de `/graph` tal cual (para leer documentos de otros modelos, p. ej. RelationDoc). */
  documents: GraphDocument[];
  /** Recarga `/graph` y `/edges`. Mantiene los datos previos mientras carga. */
  reload(): Promise<void>;
  /** Escribe un campo (`path` con la sintaxis de `core/paths`, p. ej. `status` o `tags/0`) con `expected`. Recarga. */
  saveField(docId: string, path: string, value: unknown): Promise<SaveResult>;
  /** Crea un `AtomDoc` con `POST /docs`. Recarga. */
  createAtom(name: string, payload: Payload): Promise<CreateDocumentResult>;
  /** Crea un documento de cualquier modelo (`RelationDoc`, etc.). Recarga. */
  createDocument(model: string, name: string, payload: Payload): Promise<CreateDocumentResult>;
}

export function useAtomStore(): AtomStore {
  const { client } = useSldb();
  const [state, setState] = useState<{ status: AtomStoreStatus; error: string | null; documents: GraphDocument[]; edges: Edge[] }>({
    status: "loading",
    error: null,
    documents: [],
    edges: [],
  });

  const reload = useCallback(async () => {
    try {
      const [documents, edges] = await Promise.all([client.documents(), client.getEdges()]);
      setState({ status: "ok", error: null, documents, edges });
    } catch (error) {
      setState((prev) => ({ ...prev, status: "error", error: (error as Error).message }));
    }
  }, [client]);

  useEffect(() => {
    setState({ status: "loading", error: null, documents: [], edges: [] });
    void reload();
  }, [reload]);

  const { documents } = state;
  const atoms = useMemo(() => atomsFromDocuments(documents), [documents]);
  const actas = useMemo(() => actasFromDocuments(documents), [documents]);
  const fuentes = useMemo(() => sourcesFromDocuments(documents), [documents]);
  const grupos = useMemo(() => groupInfosFromDocuments(documents), [documents]);
  const respuestas = useMemo(() => respuestasFromDocuments(documents), [documents]);
  const informes = useMemo(() => informesFromDocuments(documents), [documents]);
  const relationTypes = useMemo(() => relationTypesFromDocuments(documents), [documents]);

  const saveField = useCallback(
    async (docId: string, path: string, value: unknown) => {
      // Se relee el documento para armar `expected` con lo que SLDB tiene ahora.
      const stored = await client.document(docId);
      const result = await client.save([
        { id: docId, action: "update", model: stored.model_name, payload: setAt(stored.payload, path, value), expected: stored.payload },
      ]);
      await reload();
      return result;
    },
    [client, reload],
  );

  const createDocument = useCallback(
    async (model: string, name: string, payload: Payload) => {
      const result = await client.createDocument(model, name, payload);
      await reload();
      return result;
    },
    [client, reload],
  );
  const createAtom = useCallback((name: string, payload: Payload) => createDocument("AtomDoc", name, payload), [createDocument]);

  return { status: state.status, error: state.error, atoms, actas, fuentes, grupos, respuestas, informes, relationTypes, edges: state.edges, documents, reload, saveField, createAtom, createDocument };
}
