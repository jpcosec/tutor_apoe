/**
 * Autoridad de escritura por modelo y dueño (§4 del Manual de Usuario).
 * Módulo puro L0: sin React ni DOM.
 */
import type { AuthorityKind, ModelCatalogEntry, ModelDescription } from "./contract";

export type ModelOwner = "local" | "sldb-builtin" | "deskops";

export type EditPermission =
  | { allowed: true; operation: string; authority: AuthorityKind; owner: ModelOwner }
  | { allowed: false; reason: string; suggestedVerb?: string; authority: AuthorityKind; owner: ModelOwner };

const DESKOPS_MODELS = new Set([
  "TaskDoc",
  "TaskCodeDoc",
  "TaskDocsDoc",
  "TaskRefactorDoc",
  "TaskDebugDoc",
  "TaskDecisionDoc",
  "TaskAggregateDoc",
  "TaskExternalDoc",
  "BoardDoc",
  "PillDoc",
  "InboxNoteDoc",
  "RitualDoc",
  "RoleDoc",
  "RunDoc",
  "RuntimeProfileDoc",
  "StepDoc",
  "ReviewDoc",
  "CrossroadDoc",
  "DeskFAQDoc",
  "MaterializationContractDoc",
  "ProtoAtomDoc",
]);

/** Deduce el dueño de un modelo a partir de su `model_ref` y `name`. */
export function deduceModelOwner(modelName: string, modelRef?: string): ModelOwner {
  if (modelRef?.startsWith("deskops.") || DESKOPS_MODELS.has(modelName)) {
    return "deskops";
  }
  if (modelRef?.startsWith("sldb.models.") || modelRef?.startsWith("sldb.")) {
    return "sldb-builtin";
  }
  return "local";
}

/** ¿Se puede editar el contrato de este modelo en el Studio (Vista 04)? */
export function canEditModelContract(model: Pick<ModelCatalogEntry | ModelDescription, "name" | "model_ref">): {
  editable: boolean;
  owner: ModelOwner;
  reason?: string;
} {
  const owner = deduceModelOwner(model.name, model.model_ref);
  if (owner === "sldb-builtin") {
    return {
      editable: false,
      owner,
      reason: "Modelo builtin de SLDB (solo lectura). Cambiar su contrato requiere una tarea en sldb.",
    };
  }
  if (owner === "deskops") {
    return {
      editable: false,
      owner,
      reason: "Modelo builtin de deskops (solo lectura). Cambiar su contrato altera el desk de todos los repos.",
    };
  }
  return { editable: true, owner };
}

/**
 * Resuelve si un campo/segmento de un documento es editable en el Workbench
 * según su `__authority__` y el dueño del modelo.
 */
export function resolveFieldAuthority(
  modelName: string,
  docId: string,
  fieldPath: string,
  authority: AuthorityKind = "authored",
  modelRef?: string,
): EditPermission {
  const owner = deduceModelOwner(modelName, modelRef);

  if (authority === "source_raw") {
    return {
      allowed: false,
      authority,
      owner,
      reason: "Evidencia externa (source_raw): solo lectura. Usa la Vista 03 para anclar átomos sin romper offsets.",
    };
  }

  if (authority === "theorem") {
    return {
      allowed: false,
      authority,
      owner,
      reason: "Derivado por regla/teorema (theorem): solo lectura. Edita la fuente o el código de origen.",
    };
  }

  if (authority === "generated" || authority === "cache") {
    return {
      allowed: false,
      authority,
      owner,
      reason: `Documento ${authority}: solo lectura. Se regenera mediante operación del store.`,
    };
  }

  if (owner === "deskops") {
    const cleanId = docId.includes(":") ? docId.split(":")[1] : docId;
    const verb = modelName.startsWith("Task")
      ? `deskops edit task ${cleanId} --${fieldPath} ...`
      : `deskops (${modelName} gestionado por workflow)`;
    return {
      allowed: false,
      authority,
      owner,
      reason: "Gestionado por deskops: se modifica mediante verbos del workflow.",
      suggestedVerb: verb,
    };
  }

  return {
    allowed: true,
    authority,
    owner,
    operation: `POST /save · target=${docId}#${fieldPath}`,
  };
}
