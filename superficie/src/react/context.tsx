/**
 * Provider genérico: cliente SLDB, registro de editores y caché de schema.
 * Cualquier superficie hermana puede montar esto con su propio cliente o editores.
 */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { GraphDocument, SchemaField, SchemaModel } from "../core/contract";
import type { SldbClient } from "../core/client";
import { rootOf } from "../core/paths";
import { defaultEditors, type EditorRegistry } from "./editors/registry";

interface SldbContextValue {
  client: SldbClient;
  editors: EditorRegistry;
}

const SldbContext = createContext<SldbContextValue | null>(null);

export function SldbProvider({ client, editors, children }: { client: SldbClient; editors?: EditorRegistry; children: ReactNode }) {
  const value = useMemo(() => ({ client, editors: editors ?? defaultEditors }), [client, editors]);
  return <SldbContext.Provider value={value}>{children}</SldbContext.Provider>;
}

export function useSldb(): SldbContextValue {
  const value = useContext(SldbContext);
  if (!value) throw new Error("useSldb requiere <SldbProvider>.");
  return value;
}

export type Loadable<T> = { status: "loading" } | { status: "ready"; data: T } | { status: "error"; error: string };

export function useLoad<T>(load: () => Promise<T>, deps: unknown[]): [Loadable<T>, () => void] {
  const [state, setState] = useState<Loadable<T>>({ status: "loading" });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    load()
      .then((data) => alive && setState({ status: "ready", data }))
      .catch((error: Error) => alive && setState({ status: "error", error: error.message }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return [state, () => setTick((t) => t + 1)];
}

export interface SchemaIndex {
  models: SchemaModel[];
  errors: { model: string; error: string }[];
  field(model: string, path: string): SchemaField | undefined;
}

export function useSchema(): Loadable<SchemaIndex> {
  const { client } = useSldb();
  const [state] = useLoad(async () => {
    const response = await client.schema();
    const byModel = new Map(response.models.map((m) => [m.id, m]));
    return {
      models: response.models,
      errors: response.errors ?? [],
      field: (model: string, path: string) => byModel.get(model)?.fields.find((f) => f.name === rootOf(path)),
    };
  }, [client]);
  return state;
}

export function useDocuments(): [Loadable<GraphDocument[]>, () => void] {
  const { client } = useSldb();
  return useLoad(() => client.documents(), [client]);
}
