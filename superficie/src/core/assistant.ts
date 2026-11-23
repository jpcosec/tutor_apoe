/**
 * Cliente del asistente del Workbench. Habla con el puente local (`/assistant`, ver
 * `assistant/vite-plugin.ts`), que corre el modelo con las herramientas MCP de sldb.
 * Inyectable: las vistas reciben un `AssistantClient`, nunca llaman a `fetch`.
 */

/** Lo que la persona tiene en pantalla; viaja con cada mensaje. */
export interface AssistantContext {
  view: string;
  lens?: string | null;
  doc?: string | null;
  model?: string | null;
  path?: string | null;
  spec?: string | null;
  node?: string | null;
}

export type AssistantEvent =
  | { type: "session"; id: string }
  | { type: "delta"; text: string }
  | { type: "tool"; id: string; name: string; input: Record<string, unknown>; writes: boolean }
  | { type: "tool_result"; id: string; ok: boolean }
  | { type: "error"; message: string }
  | { type: "done"; wrote: boolean };

export interface AssistantStatus {
  available: boolean;
  detail: string;
  store: string | null;
}

export interface AssistantSendRequest {
  message: string;
  context: AssistantContext;
  sessionId?: string | null;
  signal?: AbortSignal;
}

export interface AssistantClient {
  status(): Promise<AssistantStatus>;
  /** Envía un mensaje y entrega cada evento de la respuesta a medida que llega. */
  send(request: AssistantSendRequest, onEvent: (event: AssistantEvent) => void): Promise<void>;
}

const UNAVAILABLE: AssistantStatus = {
  available: false,
  detail: "El asistente solo existe en el servidor de desarrollo (vite dev).",
  store: null,
};

function parseEvent(line: string): AssistantEvent | null {
  try {
    const parsed = JSON.parse(line) as AssistantEvent;
    return typeof parsed?.type === "string" ? parsed : null;
  } catch {
    return null;
  }
}

/** Parte un buffer en líneas completas y devuelve el resto sin terminar. */
export function splitLines(buffer: string): { lines: string[]; rest: string } {
  const parts = buffer.split("\n");
  const rest = parts.pop() ?? "";
  return { lines: parts.map((p) => p.trim()).filter(Boolean), rest };
}

export function createAssistantClient(base = "/assistant"): AssistantClient {
  return {
    async status() {
      try {
        const response = await fetch(`${base}/status`);
        if (!response.ok || !(response.headers.get("content-type") ?? "").includes("json")) return UNAVAILABLE;
        return (await response.json()) as AssistantStatus;
      } catch {
        return UNAVAILABLE;
      }
    },
    async send(request, onEvent) {
      const response = await fetch(`${base}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: request.message,
          context: request.context,
          sessionId: request.sessionId ?? undefined,
        }),
        signal: request.signal,
      });
      if (!response.ok || !response.body) {
        let message = `El asistente respondió ${response.status}`;
        try {
          const data = (await response.json()) as { error?: string };
          if (data.error) message = data.error;
        } catch {
          /* la respuesta no era JSON: queda el estado HTTP */
        }
        onEvent({ type: "error", message });
        onEvent({ type: "done", wrote: false });
        return;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        const { lines, rest } = splitLines(buffer + decoder.decode(value, { stream: true }));
        buffer = rest;
        for (const line of lines) {
          const event = parseEvent(line);
          if (event) onEvent(event);
        }
      }
      const last = parseEvent(buffer.trim());
      if (last) onEvent(last);
    },
  };
}
