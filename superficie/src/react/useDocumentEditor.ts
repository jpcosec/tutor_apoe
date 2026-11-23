/**
 * Estado de edición de un documento: carga sus segmentos, escribe por dirección de
 * field y recarga. Un field de una pieza compuesta se escribe en su documento de origen.
 * Nunca escribe Markdown: manda payload con `expected` y SLDB re-renderiza.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { DocumentSegments, Payload, SaveChange } from "../core/contract";
import { SaveConflictError, SldbHttpError } from "../core/client";
import { setAt } from "../core/paths";
import { useSldb } from "./context";

export interface WriteTarget {
  doc: string;
  model: string;
}

export type SaveState =
  | { status: "idle" }
  | { status: "saving"; key: string }
  | { status: "saved"; at: number }
  | { status: "conflict"; message: string; doc: string; path: string; value: unknown }
  | { status: "error"; message: string; key: string };

export const editKey = (target: WriteTarget, path: string) => `${target.doc}::${path}`;

export function useDocumentEditor(id: string) {
  const { client } = useSldb();
  const [data, setData] = useState<DocumentSegments | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [save, setSave] = useState<SaveState>({ status: "idle" });

  // Id vigente: una respuesta lenta de un documento anterior no pisa al actual.
  const currentId = useRef(id);
  currentId.current = id;

  const reload = useCallback(async () => {
    if (!id) return;
    try {
      const next = await client.segments(id);
      if (currentId.current !== id) return;
      setData(next);
      setLoadError(null);
    } catch (error) {
      if (currentId.current !== id) return;
      setLoadError((error as Error).message);
    }
  }, [client, id]);

  useEffect(() => {
    setData(null);
    setSave({ status: "idle" });
    void reload();
  }, [reload]);

  const baseFor = useCallback(
    async (target: WriteTarget): Promise<{ payload: Payload; model: string }> => {
      if (data && target.doc === data.id) return { payload: data.payload, model: data.model };
      const stored = await client.document(target.doc);
      return { payload: stored.payload, model: stored.model_name };
    },
    [client, data],
  );

  const write = useCallback(
    async (target: WriteTarget, key: string, build: (payload: Payload) => Payload, path: string, value: unknown) => {
      setSave({ status: "saving", key });
      try {
        const base = await baseFor(target);
        const change: SaveChange = { id: target.doc, action: "update", model: base.model, payload: build(base.payload), expected: base.payload };
        await client.save([change]);
        await reload();
        setSave({ status: "saved", at: Date.now() });
      } catch (error) {
        if (error instanceof SaveConflictError) {
          setSave({ status: "conflict", message: error.message, doc: target.doc, path, value });
        } else {
          const message = error instanceof SldbHttpError ? error.message : String(error);
          setSave({ status: "error", message, key });
        }
      }
    },
    [baseFor, client, reload],
  );

  /** Cambia el valor de un field. */
  const commit = useCallback(
    (target: WriteTarget, path: string, value: unknown) =>
      write(target, editKey(target, path), (payload) => setAt(payload, path, value), path, value),
    [write],
  );

  /** Reemplaza el payload entero de este documento (reordenar composiciones, operaciones de lista). */
  const commitPayload = useCallback(
    (path: string, next: (payload: Payload) => Payload) =>
      data ? write({ doc: data.id, model: data.model }, editKey({ doc: data.id, model: data.model }, path), next, path, null) : Promise.resolve(),
    [data, write],
  );

  const dismiss = useCallback(() => setSave({ status: "idle" }), []);

  return { data, loadError, save, reload, commit, commitPayload, dismiss };
}
