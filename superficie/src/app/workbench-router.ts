import type { WorkbenchLens } from "../workbench/ProsaWorkbenchView";

export type WorkbenchViewId = "workbench" | "diagram" | "source" | "studio";

export interface WorkbenchRouteState {
  view: WorkbenchViewId;
  doc: string | null;
  lens: WorkbenchLens;
  spec: string | null;
  node: string | null;
  model: string | null;
}

export function parseWorkbenchHash(hash: string): WorkbenchRouteState {
  const cleaned = hash.replace(/^#\/?/, "").trim();
  const [pathPart, queryPart = ""] = cleaned.split("?");
  const params = new URLSearchParams(queryPart);

  let view: WorkbenchViewId = "workbench";
  if (pathPart === "diagram" || pathPart === "spec2viz") {
    view = "diagram";
  } else if (pathPart === "source" || pathPart === "anchoring") {
    view = "source";
  } else if (pathPart === "studio" || pathPart === "models") {
    view = "studio";
  }

  const rawLens = params.get("lens");
  const lens: WorkbenchLens = rawLens === "fierros" ? "fierros" : "lectura";

  return {
    view,
    doc: params.get("doc"),
    lens,
    spec: params.get("spec"),
    node: params.get("node"),
    model: params.get("model"),
  };
}

export function formatWorkbenchHash(
  state: Partial<WorkbenchRouteState> & { view: WorkbenchViewId },
): string {
  const params = new URLSearchParams();
  if (state.doc) params.set("doc", state.doc);
  // La lente sobrevive a la recarga en prosa, diagrama y fuente; studio no tiene lente.
  if (state.view !== "studio" && state.lens) params.set("lens", state.lens);
  if (state.spec) params.set("spec", state.spec);
  if (state.node) params.set("node", state.node);
  if (state.model) params.set("model", state.model);
  const qs = params.toString();
  return `#/${state.view}${qs ? `?${qs}` : ""}`;
}
