import React, { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AssistantClient, AssistantContext, AssistantEvent, AssistantStatus } from "../core/assistant";

export interface AssistantDockProps {
  client: AssistantClient;
  /** Lo que hay en pantalla ahora; se envía con cada mensaje. */
  context: AssistantContext;
  /** Texto corto de ese contexto para mostrarlo en el panel. */
  contextLabel: string;
  /** El asistente escribió en el store: hay que volver a leerlo. */
  onStoreChanged(): void;
  onClose(): void;
}

interface ToolCall {
  id: string;
  name: string;
  writes: boolean;
  ok: boolean | null;
}

export interface ChatTurn {
  role: "user" | "assistant";
  text: string;
  tools: ToolCall[];
  error: string | null;
}

const emptyAssistantTurn = (): ChatTurn => ({ role: "assistant", text: "", tools: [], error: null });

/** Aplica un evento de la respuesta al turno del asistente que se está escribiendo. */
export function applyEvent(turn: ChatTurn, event: AssistantEvent): ChatTurn {
  switch (event.type) {
    case "delta":
      return { ...turn, text: turn.text + event.text };
    case "tool":
      // Lo que el asistente dice después de una operación es otro párrafo.
      return { ...turn, text: turn.text && !turn.text.endsWith("\n") ? `${turn.text}\n\n` : turn.text, tools: [...turn.tools, { id: event.id, name: event.name, writes: event.writes, ok: null }] };
    case "tool_result":
      return { ...turn, tools: turn.tools.map((t) => (t.id === event.id ? { ...t, ok: event.ok } : t)) };
    case "error":
      return { ...turn, error: event.message };
    default:
      return turn;
  }
}

export const AssistantDock: React.FC<AssistantDockProps> = ({
  client,
  context,
  contextLabel,
  onStoreChanged,
  onClose,
}) => {
  const [status, setStatus] = useState<AssistantStatus | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const sessionRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const logRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    let alive = true;
    client.status().then((s) => alive && setStatus(s));
    return () => {
      alive = false;
    };
  }, [client]);

  useEffect(() => {
    inputRef.current?.focus();
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [turns]);

  const send = useCallback(async () => {
    const message = draft.trim();
    if (!message || busy) return;
    setDraft("");
    setBusy(true);
    setTurns((prev) => [...prev, { role: "user", text: message, tools: [], error: null }, emptyAssistantTurn()]);
    const controller = new AbortController();
    abortRef.current = controller;
    const patchLast = (fn: (turn: ChatTurn) => ChatTurn) =>
      setTurns((prev) => prev.map((turn, i) => (i === prev.length - 1 ? fn(turn) : turn)));
    try {
      await client.send(
        { message, context, sessionId: sessionRef.current, signal: controller.signal },
        (event) => {
          if (event.type === "session") sessionRef.current = event.id;
          else if (event.type === "done") {
            if (event.wrote) onStoreChanged();
          } else patchLast((turn) => applyEvent(turn, event));
        },
      );
    } catch (error) {
      if (!controller.signal.aborted) {
        patchLast((turn) => ({
          ...turn,
          error: error instanceof Error ? error.message : "Se cortó la conexión con el asistente",
        }));
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }, [busy, client, context, draft, onStoreChanged]);

  const unavailable = status !== null && !status.available;

  return (
    <section className="wb-assistant" aria-label="Asistente" data-testid="assistant-dock">
      <header className="wb-assistant__head">
        <span className="wb-assistant__title">asistente</span>
        <span className="wb-assistant__ctx" title="Lo que el asistente sabe que estás viendo" data-testid="assistant-context">
          {contextLabel}
        </span>
        <button type="button" className="wb-assistant__close" onClick={onClose} aria-label="Cerrar el asistente">
          <svg viewBox="0 0 12 12" aria-hidden="true">
            <path d="M2.5 2.5l7 7M9.5 2.5l-7 7" />
          </svg>
        </button>
      </header>

      <div className="wb-assistant__log" ref={logRef} aria-live="polite">
        {turns.length === 0 && !unavailable && (
          <p className="wb-assistant__hint">
            Pídele que lea, busque o edite sobre lo que estás viendo. Trabaja solo con las operaciones de SLDB y
            muestra cada una que usa.
          </p>
        )}
        {unavailable && (
          <p className="wb-assistant__error" data-testid="assistant-unavailable">
            El asistente no está disponible: {status?.detail}
          </p>
        )}
        {turns.map((turn, i) => (
          <div key={i} className={`wb-assistant__turn wb-assistant__turn--${turn.role}`}>
            {turn.tools.length > 0 && (
              <ul className="wb-assistant__tools">
                {turn.tools.map((tool) => (
                  <li
                    key={tool.id}
                    className={tool.writes ? "wb-assistant__tool wb-assistant__tool--write" : "wb-assistant__tool"}
                    data-testid="assistant-tool"
                  >
                    <span>sldb · {tool.name}</span>
                    <span className="wb-assistant__tool-state">
                      {tool.ok === null ? "…" : tool.ok ? (tool.writes ? "escrito" : "ok") : "falló"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {turn.text &&
              (turn.role === "assistant" ? (
                <div className="wb-assistant__text wb-assistant__text--md">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.text}</ReactMarkdown>
                </div>
              ) : (
                <div className="wb-assistant__text">{turn.text}</div>
              ))}
            {turn.role === "assistant" && !turn.text && !turn.error && busy && i === turns.length - 1 && (
              <div className="wb-assistant__pending">pensando…</div>
            )}
            {turn.error && (
              <div className="wb-assistant__error" data-testid="assistant-error">
                {turn.error}
              </div>
            )}
          </div>
        ))}
      </div>

      <form
        className="wb-assistant__form"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <textarea
          ref={inputRef}
          className="wb-assistant__input"
          rows={2}
          value={draft}
          placeholder={unavailable ? "No disponible" : "Escribe qué quieres hacer con este documento"}
          disabled={unavailable}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            } else if (e.key === "Escape") {
              e.stopPropagation();
              onClose();
            }
          }}
          aria-label="Mensaje para el asistente"
          data-testid="assistant-input"
        />
        {busy ? (
          <button
            type="button"
            className="wb-btn"
            onClick={() => abortRef.current?.abort()}
            data-testid="assistant-stop"
          >
            Detener
          </button>
        ) : (
          <button
            type="submit"
            className="wb-btn wb-btn--primary"
            disabled={unavailable || !draft.trim()}
            data-testid="assistant-send"
          >
            Enviar
          </button>
        )}
      </form>
    </section>
  );
};
