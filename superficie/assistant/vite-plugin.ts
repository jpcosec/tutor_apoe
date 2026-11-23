/**
 * Puente local del asistente del Workbench (solo `vite dev`).
 *
 * `POST /assistant/chat` lanza un `claude -p` (la sesión de Claude Code de quien corre el
 * servidor de desarrollo; no usa API key) con UN solo conjunto de herramientas: el servidor
 * MCP de sldb (`sldb mcp --store <store> --level 1`) sobre el mismo store que sirve
 * `sldb serve`. La respuesta se entrega como líneas JSON (`AssistantEvent`).
 *
 * El asistente no tiene herramientas de archivos ni de shell: todo lo que escribe pasa por
 * una operación con nombre del MCP de sldb, firmada como `agent:workbench-assistant`.
 */
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import type { Plugin } from "vite";

export interface AssistantPluginOptions {
  /** URL del `sldb serve` que alimenta la UI; de ahí se lee qué store editar. */
  sldbTarget: string;
}

interface StoreInfo {
  store: string;
  root: string;
}

const MAX_BODY = 32 * 1024;
const READ_ONLY = /^(read_|list_|describe_|select_|resolve_|check_|neighbors$|neighborhood$)/;

const SYSTEM_PROMPT = [
  "Eres el asistente del SLDB Workbench, la interfaz de un store SLDB.",
  "Trabajas SOLO con las herramientas del servidor MCP `sldb`; no tienes archivos ni terminal.",
  "La persona está mirando un documento en pantalla; el contexto de lo que ve viene en cada mensaje.",
  "Reglas:",
  "- Lee antes de escribir: usa read_document o select_documents para confirmar ids, modelo y contenido.",
  "- Antes de una escritura di en una línea qué vas a cambiar. Después di qué operación corrió y su resultado.",
  "- Si una herramienta falla, cita el error tal cual y propone el siguiente paso. No inventes contenido ni ids.",
  "- Si lo pedido no se puede hacer con estas herramientas, dilo; no lo simules.",
  "- Responde en español, breve, en texto plano con a lo más listas cortas.",
].join("\n");

function sendJson(res: ServerResponse, status: number, payload: unknown): void {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(payload));
}

/** Un endpoint local que lanza procesos no acepta pedidos de otra página. */
function sameOrigin(req: IncomingMessage): boolean {
  const origin = req.headers.origin;
  if (!origin) return true;
  try {
    return new URL(origin).host === req.headers.host;
  } catch {
    return false;
  }
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => {
      size += chunk.length;
      if (size > MAX_BODY) {
        reject(new Error("El mensaje es demasiado largo"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf-8")));
    req.on("error", reject);
  });
}

function claudeBin(): string {
  return process.env.WORKBENCH_ASSISTANT_CLAUDE ?? "claude";
}

function pythonBin(): string {
  return process.env.SLDB_PYTHON ?? "python3";
}

let claudeChecked: { ok: boolean; detail: string } | null = null;
function checkClaude(): { ok: boolean; detail: string } {
  if (claudeChecked) return claudeChecked;
  const probe = spawnSync(claudeBin(), ["--version"], { encoding: "utf-8", timeout: 15000 });
  claudeChecked =
    probe.status === 0
      ? { ok: true, detail: probe.stdout.trim() }
      : { ok: false, detail: `No encontré el CLI \`${claudeBin()}\` en este equipo` };
  return claudeChecked;
}

async function storeInfo(sldbTarget: string): Promise<StoreInfo> {
  const response = await fetch(`${sldbTarget.replace(/\/$/, "")}/stores`);
  if (!response.ok) throw new Error(`sldb serve respondió ${response.status} en /stores`);
  const data = (await response.json()) as Partial<StoreInfo>;
  if (!data.store || !data.root) throw new Error("sldb serve no informó la ruta del store");
  return { store: data.store, root: data.root };
}

/** Config MCP de la corrida: el servidor de sldb sobre el store que la UI está mostrando. */
function writeMcpConfig(info: StoreInfo): string {
  const dir = join(tmpdir(), "sldb-workbench-assistant");
  mkdirSync(dir, { recursive: true });
  const pythonpath = [process.env.SLDB_PYTHONPATH, info.root, dirname(info.root)].filter(Boolean).join(":");
  const config = {
    mcpServers: {
      sldb: {
        command: pythonBin(),
        args: ["-m", "sldb", "mcp", "--store", info.store, "--level", "1", "--actor", "agent:workbench-assistant"],
        env: { PYTHONPATH: pythonpath },
      },
    },
  };
  const path = join(dir, "mcp.json");
  writeFileSync(path, JSON.stringify(config), "utf-8");
  return path;
}

function contextBlock(context: Record<string, unknown>, info: StoreInfo): string {
  const line = (label: string, key: string) =>
    typeof context[key] === "string" && context[key] ? `- ${label}: ${String(context[key])}` : null;
  return [
    "[Lo que la persona tiene en pantalla]",
    `- store: ${info.store}`,
    line("vista", "view"),
    line("lente", "lens"),
    line("documento", "doc"),
    line("modelo del documento", "model"),
    line("ruta del archivo", "path"),
    line("diagrama", "spec"),
    line("nodo del diagrama", "node"),
  ]
    .filter(Boolean)
    .join("\n");
}

interface ChatRequest {
  message: string;
  sessionId?: string;
  context?: Record<string, unknown>;
}

async function handleChat(req: IncomingMessage, res: ServerResponse, options: AssistantPluginOptions): Promise<void> {
  let request: ChatRequest;
  try {
    request = JSON.parse(await readBody(req)) as ChatRequest;
  } catch (error) {
    sendJson(res, 400, { error: error instanceof Error ? error.message : "Pedido inválido" });
    return;
  }
  if (typeof request.message !== "string" || !request.message.trim()) {
    sendJson(res, 400, { error: "Falta el mensaje" });
    return;
  }
  if (request.sessionId && !/^[0-9a-f-]{36}$/.test(request.sessionId)) {
    sendJson(res, 400, { error: "Sesión inválida" });
    return;
  }
  const claude = checkClaude();
  if (!claude.ok) {
    sendJson(res, 503, { error: claude.detail });
    return;
  }
  let info: StoreInfo;
  try {
    info = await storeInfo(options.sldbTarget);
  } catch (error) {
    sendJson(res, 502, { error: error instanceof Error ? error.message : "No pude leer el store" });
    return;
  }

  const prompt = `${contextBlock(request.context ?? {}, info)}\n\n[Mensaje]\n${request.message.trim()}`;
  const args = [
    "-p",
    prompt,
    "--mcp-config",
    writeMcpConfig(info),
    "--strict-mcp-config",
    "--tools",
    "",
    "--allowedTools",
    "mcp__sldb",
    "--setting-sources",
    "",
    "--system-prompt",
    SYSTEM_PROMPT,
    "--model",
    process.env.WORKBENCH_ASSISTANT_MODEL ?? "sonnet",
    "--output-format",
    "stream-json",
    "--verbose",
    "--include-partial-messages",
  ];
  if (request.sessionId) args.push("--resume", request.sessionId);

  res.statusCode = 200;
  res.setHeader("Content-Type", "application/x-ndjson; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("X-Accel-Buffering", "no");
  const emit = (event: Record<string, unknown>) => res.write(`${JSON.stringify(event)}\n`);

  const child = spawn(claudeBin(), args, {
    cwd: join(tmpdir(), "sldb-workbench-assistant"),
    stdio: ["ignore", "pipe", "pipe"],
  });
  res.on("close", () => {
    if (child.exitCode === null) child.kill("SIGTERM");
  });

  const toolNames = new Map<string, string>();
  let wrote = false;
  let finished = false;
  let stderr = "";
  let pending = "";

  const handleLine = (raw: string) => {
    let event: Record<string, any>;
    try {
      event = JSON.parse(raw) as Record<string, any>;
    } catch {
      return;
    }
    if (event.type === "system" && event.subtype === "init") {
      emit({ type: "session", id: event.session_id });
      const server = (event.mcp_servers as { name: string; status: string }[] | undefined)?.find(
        (s) => s.name === "sldb",
      );
      if (server && server.status !== "connected") {
        emit({
          type: "error",
          message: `El servidor MCP de sldb no arrancó (${server.status}). Revisa que \`${pythonBin()} -m sldb mcp\` funcione: necesita el extra \`mcp\`.`,
        });
      }
    } else if (event.type === "stream_event") {
      const delta = event.event?.delta;
      if (event.event?.type === "content_block_delta" && delta?.type === "text_delta" && delta.text) {
        emit({ type: "delta", text: delta.text });
      }
    } else if (event.type === "assistant") {
      for (const block of event.message?.content ?? []) {
        if (block.type === "tool_use") {
          const name = String(block.name).replace(/^mcp__sldb__/, "");
          toolNames.set(block.id, name);
          emit({ type: "tool", id: block.id, name, input: block.input ?? {}, writes: !READ_ONLY.test(name) });
        }
      }
    } else if (event.type === "user") {
      for (const block of event.message?.content ?? []) {
        if (block?.type !== "tool_result") continue;
        const name = toolNames.get(block.tool_use_id) ?? "";
        const ok = block.is_error !== true;
        if (ok && name && !READ_ONLY.test(name)) wrote = true;
        emit({ type: "tool_result", id: block.tool_use_id, ok });
      }
    } else if (event.type === "result") {
      finished = true;
      if (event.is_error) emit({ type: "error", message: String(event.result ?? "La corrida terminó con error") });
      emit({ type: "done", wrote });
    }
  };

  child.stdout.on("data", (chunk: Buffer) => {
    pending += chunk.toString("utf-8");
    let cut = pending.indexOf("\n");
    while (cut !== -1) {
      const line = pending.slice(0, cut).trim();
      pending = pending.slice(cut + 1);
      if (line) handleLine(line);
      cut = pending.indexOf("\n");
    }
  });
  child.stderr.on("data", (chunk: Buffer) => {
    stderr = (stderr + chunk.toString("utf-8")).slice(-2000);
  });
  child.on("error", (error) => {
    emit({ type: "error", message: `No pude lanzar ${claudeBin()}: ${error.message}` });
    emit({ type: "done", wrote });
    res.end();
  });
  child.on("close", (code) => {
    if (!finished) {
      emit({
        type: "error",
        message: stderr.trim() || `El asistente terminó sin responder (código ${code ?? "?"})`,
      });
      emit({ type: "done", wrote });
    }
    res.end();
  });
}

export function assistantPlugin(options: AssistantPluginOptions): Plugin {
  return {
    name: "sldb-workbench-assistant",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use("/assistant", (req, res, next) => {
        const route = (req.url ?? "").split("?")[0];
        if (!sameOrigin(req)) {
          sendJson(res, 403, { error: "Origen no permitido" });
          return;
        }
        if (req.method === "GET" && route === "/status") {
          const claude = checkClaude();
          storeInfo(options.sldbTarget)
            .then((info) => sendJson(res, 200, { available: claude.ok, detail: claude.detail, store: info.store }))
            .catch((error: unknown) =>
              sendJson(res, 200, {
                available: false,
                detail: error instanceof Error ? error.message : "sldb serve no responde",
                store: null,
              }),
            );
          return;
        }
        if (req.method === "POST" && route === "/chat") {
          void handleChat(req, res, options);
          return;
        }
        next();
      });
    },
  };
}
