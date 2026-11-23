/**
 * Cliente HTTP de `sldb serve`. Framework-agnóstico: solo usa `fetch`.
 * Toda escritura va por `/save` en modo batch con `expected` (control optimista).
 */
import type {
  CreateDocumentResult,
  FieldRankHit,
  DocumentSegments,
  Edge,
  ExtractionSegments,
  GraphDocument,
  LintReport,
  Payload,
  RankHit,
  RankParams,
  SaveChange,
  SaveResult,
  SchemaResponse,
  SimilarNode,
  StoresCheck,
  SimilarityResult,
  StoredDocument,
  ModelCatalogEntry,
  ModelDescription,
  ModelDraftOpResult,
  ModelValidationReport,
  ResolvedNotationView,
  AuthorityKind,
} from "./contract";

export class SldbHttpError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body: unknown,
  ) {
    super(message);
    this.name = "SldbHttpError";
  }
}

/** El documento cambió en SLDB desde que se leyó: la escritura se rechazó sin tocar nada. */
export class SaveConflictError extends SldbHttpError {
  constructor(message: string, body: unknown) {
    super(message, 409, body);
    this.name = "SaveConflictError";
  }
}

export interface SldbClient {
  schema(): Promise<SchemaResponse>;
  documents(): Promise<GraphDocument[]>;
  document(id: string): Promise<StoredDocument>;
  segments(id: string): Promise<DocumentSegments>;
  extract(model: string, markdown: string): Promise<ExtractionSegments>;
  save(changes: SaveChange[]): Promise<SaveResult>;
  /** Aristas del grafo; con `id` (`Model:name`) solo las que tocan ese documento. */
  getEdges(id?: string): Promise<Edge[]>;
  /** `GET /render?doc=`: markdown del documento tal como lo renderiza SLDB (con su frontmatter). */
  render(id: string): Promise<string>;
  /** Crea un documento nuevo (`POST /docs`). Errores 400/404/409/422 lanzan `SldbHttpError`. */
  createDocument(model: string, name: string, payload: Payload): Promise<CreateDocumentResult>;
  /** `GET /corpus/rank`. Devuelve un resultado de tres estados, nunca lanza por 409/404/red. */
  rank(params: RankParams & { fields?: false }): Promise<SimilarityResult<RankHit>>;
  rank(params: RankParams & { fields: true }): Promise<SimilarityResult<FieldRankHit>>;
  /** `GET /similar`: vecinos por grafo de un nodo (`Model:name`), con los mismos tres estados. */
  similar(id: string, opts?: { relations?: string[]; limit?: number; types?: string[] }): Promise<SimilarityResult<SimilarNode>>;
  /** `GET /stores/check`: integridad y divergencia modelo vs archivo en disco. */
  storesCheck(): Promise<StoresCheck>;
  /** Análisis que SLDB ya sirve; no se deriva nada de esto en el cliente. */
  lint(): Promise<LintReport>;
  isolated(): Promise<string[]>;
  cycles(limit?: number): Promise<string[][]>;
  /** SV02: Vista de notación resuelta (`GET /notations/view?spec=`). */
  notationView(spec: string): Promise<ResolvedNotationView>;
  /** SV04: Catálogo de modelos (`GET /models`). */
  modelsCatalog(): Promise<ModelCatalogEntry[]>;
  /** SV04: Descripción completa del contrato de un modelo (`GET /models/detail?model=`). */
  describeModel(model: string): Promise<ModelDescription>;
  /** SV04: Operaciones de edición draft, validación y promoción de modelos (`POST /models/*`). */
  addModelField(model: string, fieldName: string, fieldType: string, description: string, defaultValue?: unknown): Promise<ModelDraftOpResult>;
  removeModelField(model: string, fieldName: string): Promise<ModelDraftOpResult>;
  editModelMetadata(
    model: string,
    metadata: {
      authority?: AuthorityKind;
      containment?: Record<string, string[]>;
      references?: string[];
      compositions?: Record<string, unknown>;
      semantics?: Record<string, string[]>;
    },
  ): Promise<ModelDraftOpResult>;
  editModelTemplate(model: string, content: string): Promise<ModelDraftOpResult>;
  validateModelDraft(model: string): Promise<ModelValidationReport>;
  promoteModelDraft(model: string, backfill?: boolean): Promise<ModelValidationReport>;
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

function errorMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "error" in body && typeof body.error === "string") {
    return body.error;
  }
  return `SLDB respondió ${status}`;
}

function rankQuery(p: RankParams): string {
  const q = new URLSearchParams({ q: p.q });
  if (p.k !== undefined) q.set("k", String(p.k));
  if (p.threshold !== undefined) q.set("threshold", String(p.threshold));
  if (p.among?.length) q.set("among", p.among.join(","));
  if (p.fields) q.set("fields", "1");
  if (p.refresh) q.set("refresh", "1");
  return q.toString();
}

/** 200 → ok; 409 `not_indexed` → not_indexed; cualquier otra cosa (404, red, cuerpo raro) → unavailable. */
async function similarity<T>(fetchImpl: FetchLike, url: string, pick: (body: unknown) => T[] | null): Promise<SimilarityResult<T>> {
  try {
    const response = await fetchImpl(url);
    const body: unknown = await response.json().catch(() => null);
    if (response.status === 409 && (body as { kind?: string } | null)?.kind === "not_indexed") return { status: "not_indexed" };
    const hits = response.ok ? pick(body) : null;
    if (hits) return { status: "ok", hits };
    return { status: "unavailable", reason: errorMessage(body, response.status) };
  } catch (error) {
    return { status: "unavailable", reason: error instanceof Error ? error.message : "sin respuesta" };
  }
}

export function createHttpClient(baseUrl: string, fetchImpl: FetchLike = (i, init) => fetch(i, init)): SldbClient {
  const root = baseUrl.replace(/\/$/, "");

  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetchImpl(`${root}${path}`, init);
    const body: unknown = await response.json().catch(() => null);
    if (response.status === 409) throw new SaveConflictError(errorMessage(body, 409), body);
    if (!response.ok) throw new SldbHttpError(errorMessage(body, response.status), response.status, body);
    return body as T;
  }

  const post = <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

  return {
    schema: () => request<SchemaResponse>("/schema"),
    documents: async () => (await request<{ documents: GraphDocument[] }>("/graph")).documents,
    document: (id) => request<StoredDocument>(`/document?id=${encodeURIComponent(id)}`),
    segments: (id) => request<DocumentSegments>(`/document/segments?id=${encodeURIComponent(id)}`),
    extract: (model, markdown) => post<ExtractionSegments>("/extract/segments", { model, markdown }),
    save: (changes) => post<SaveResult>("/save", { changes }),
    getEdges: async (id) => (await request<{ edges: Edge[] }>(id ? `/edges?id=${encodeURIComponent(id)}` : "/edges")).edges,
    render: async (id) => (await request<{ markdown: string }>(`/render?doc=${encodeURIComponent(id)}`)).markdown,
    createDocument: (model, name, payload) => post<CreateDocumentResult>("/docs", { model, name, payload }),
    rank: ((p: RankParams) =>
      similarity(fetchImpl, `${root}/corpus/rank?${rankQuery(p)}`, (b) => ((b as { hits?: unknown[] })?.hits ?? null) as never)) as SldbClient["rank"],
    similar: (id, opts = {}) => {
      const q = new URLSearchParams({ id });
      if (opts.relations?.length) q.set("relations", opts.relations.join(","));
      if (opts.limit !== undefined) q.set("limit", String(opts.limit));
      if (opts.types?.length) q.set("types", opts.types.join(","));
      return similarity<SimilarNode>(fetchImpl, `${root}/similar?${q}`, (b) => ((b as { similar?: SimilarNode[] })?.similar ?? null));
    },
    storesCheck: () => request<StoresCheck>("/stores/check"),
    lint: () => request<LintReport>("/lint"),
    isolated: async () => (await request<{ isolated: string[] }>("/graph/isolated")).isolated,
    cycles: async (limit = 20) => (await request<{ cycles: string[][] }>(`/graph/cycles?limit=${limit}`)).cycles,
    notationView: (spec) => request<ResolvedNotationView>(`/notations/view?spec=${encodeURIComponent(spec.replace(/^SpecDoc:/, ""))}`),
    modelsCatalog: async () => (await request<{ models: ModelCatalogEntry[] }>("/models")).models,
    describeModel: async (model) => {
      const res = await request<{ ok: boolean; model?: ModelDescription; error?: string }>(`/models/detail?model=${encodeURIComponent(model)}`);
      if (!res.ok || !res.model) throw new SldbHttpError(res.error ?? `No se pudo describir ${model}`, 400, res);
      return res.model;
    },
    addModelField: (model, field_name, field_type, description, defaultVal) =>
      post<ModelDraftOpResult>("/models/fields-add", { model, field_name, field_type, description, default: defaultVal }),
    removeModelField: (model, field_name) =>
      post<ModelDraftOpResult>("/models/fields-remove", { model, field_name }),
    editModelMetadata: (model, metadata) =>
      post<ModelDraftOpResult>("/models/metadata-edit", { model, ...metadata }),
    editModelTemplate: (model, content) =>
      post<ModelDraftOpResult>("/models/template-edit", { model, content }),
    validateModelDraft: (model) =>
      post<ModelValidationReport>("/models/validate", { model }),
    promoteModelDraft: (model, backfill = false) =>
      post<ModelValidationReport>("/models/promote", { model, backfill }),
  };
}
