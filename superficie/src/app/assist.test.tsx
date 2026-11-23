import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { splitLines } from "../core/assistant";
import type { AssistantClient, AssistantEvent, AssistantSendRequest } from "../core/assistant";
import { applyEvent } from "./AssistantDock";
import type { ChatTurn } from "./AssistantDock";
import { placeCard } from "./TourOverlay";
import { TOUR_STEPS } from "./tour-steps";
import { WorkbenchAssist } from "./WorkbenchAssist";

const CONTEXT = { view: "workbench", lens: "fierros", doc: "rep-01", model: "InformeDoc", path: "docs/rep-01.md" };

/** Cliente de asistente en memoria: responde con los eventos que se le entregan. */
function scriptedClient(events: AssistantEvent[], available = true) {
  const sent: AssistantSendRequest[] = [];
  const client: AssistantClient = {
    status: async () => ({
      available,
      detail: available ? "claude 2.x" : "No encontré el CLI `claude` en este equipo",
      store: "/tmp/s/.sldb",
    }),
    send: async (request, onEvent) => {
      sent.push(request);
      for (const event of events) onEvent(event);
    },
  };
  return { client, sent };
}

function renderAssist(client: AssistantClient, extra: Partial<React.ComponentProps<typeof WorkbenchAssist>> = {}) {
  const onStoreChanged = vi.fn();
  const onTourGo = vi.fn();
  render(
    <WorkbenchAssist
      assistantClient={client}
      context={CONTEXT}
      contextLabel="InformeDoc / rep-01 · prosa · fierros visibles"
      onStoreChanged={onStoreChanged}
      onTourGo={onTourGo}
      {...extra}
    />,
  );
  return { onStoreChanged, onTourGo };
}

describe("asistente", () => {
  it("envía el mensaje con lo que hay en pantalla y muestra las operaciones y la respuesta", async () => {
    const { client, sent } = scriptedClient([
      { type: "session", id: "11111111-2222-3333-4444-555555555555" },
      { type: "tool", id: "t1", name: "read_document", input: { ref: "InformeDoc:rep-01" }, writes: false },
      { type: "tool_result", id: "t1", ok: true },
      { type: "delta", text: "El título es " },
      { type: "delta", text: "Informe Principal." },
      { type: "done", wrote: false },
    ]);
    const { onStoreChanged } = renderAssist(client);

    fireEvent.click(screen.getByTestId("assist-open-assistant"));
    expect(screen.getByTestId("assistant-context")).toHaveTextContent("InformeDoc / rep-01");
    fireEvent.change(screen.getByTestId("assistant-input"), { target: { value: "¿Cuál es el título?" } });
    fireEvent.click(screen.getByTestId("assistant-send"));

    await waitFor(() => expect(screen.getByText("El título es Informe Principal.")).toBeInTheDocument());
    expect(sent[0]?.message).toBe("¿Cuál es el título?");
    expect(sent[0]?.context).toEqual(CONTEXT);
    expect(sent[0]?.sessionId).toBeNull();
    expect(screen.getByTestId("assistant-tool")).toHaveTextContent("sldb · read_document");
    expect(screen.getByTestId("assistant-tool")).toHaveTextContent("ok");
    expect(onStoreChanged).not.toHaveBeenCalled();
  });

  it("avisa que el store cambió cuando el asistente escribió, y sigue en la misma sesión", async () => {
    const { client, sent } = scriptedClient([
      { type: "session", id: "11111111-2222-3333-4444-555555555555" },
      { type: "tool", id: "t1", name: "write_document", input: {}, writes: true },
      { type: "tool_result", id: "t1", ok: true },
      { type: "delta", text: "Listo." },
      { type: "done", wrote: true },
    ]);
    const { onStoreChanged } = renderAssist(client);
    fireEvent.click(screen.getByTestId("assist-open-assistant"));

    fireEvent.change(screen.getByTestId("assistant-input"), { target: { value: "Cambia la versión" } });
    fireEvent.keyDown(screen.getByTestId("assistant-input"), { key: "Enter" });
    await waitFor(() => expect(onStoreChanged).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId("assistant-tool")).toHaveTextContent("escrito");

    fireEvent.change(screen.getByTestId("assistant-input"), { target: { value: "Y ahora otra cosa" } });
    fireEvent.keyDown(screen.getByTestId("assistant-input"), { key: "Enter" });
    await waitFor(() => expect(sent).toHaveLength(2));
    expect(sent[1]?.sessionId).toBe("11111111-2222-3333-4444-555555555555");
  });

  it("muestra el error de una corrida y no avisa cambios", async () => {
    const { client } = scriptedClient([
      { type: "error", message: "El servidor MCP de sldb no arrancó (failed)." },
      { type: "done", wrote: false },
    ]);
    const { onStoreChanged } = renderAssist(client);
    fireEvent.click(screen.getByTestId("assist-open-assistant"));
    fireEvent.change(screen.getByTestId("assistant-input"), { target: { value: "hola" } });
    fireEvent.click(screen.getByTestId("assistant-send"));
    await waitFor(() => expect(screen.getByTestId("assistant-error")).toHaveTextContent("no arrancó"));
    expect(onStoreChanged).not.toHaveBeenCalled();
  });

  it("dice por qué no está disponible y deshabilita el envío", async () => {
    const { client } = scriptedClient([], false);
    renderAssist(client);
    fireEvent.click(screen.getByTestId("assist-open-assistant"));
    await waitFor(() => expect(screen.getByTestId("assistant-unavailable")).toHaveTextContent("No encontré el CLI"));
    expect(screen.getByTestId("assistant-input")).toBeDisabled();
    expect(screen.getByTestId("assistant-send")).toBeDisabled();
  });

  it("applyEvent acumula texto y cierra cada operación con su resultado", () => {
    let turn: ChatTurn = { role: "assistant", text: "", tools: [], error: null };
    turn = applyEvent(turn, { type: "tool", id: "a", name: "select_documents", input: {}, writes: false });
    turn = applyEvent(turn, { type: "tool_result", id: "a", ok: false });
    turn = applyEvent(turn, { type: "delta", text: "No " });
    turn = applyEvent(turn, { type: "delta", text: "encontré." });
    expect(turn.text).toBe("No encontré.");
    expect(turn.tools).toEqual([{ id: "a", name: "select_documents", writes: false, ok: false }]);
  });

  it("splitLines devuelve las líneas completas y guarda la que quedó a medias", () => {
    expect(splitLines('{"a":1}\n{"b":2}\n{"c"')).toEqual({ lines: ['{"a":1}', '{"b":2}'], rest: '{"c"' });
    expect(splitLines("\n\n")).toEqual({ lines: [], rest: "" });
  });
});

describe("recorrido", () => {
  it("abre en el primer paso, avanza, retrocede y lleva a la vista de cada paso", () => {
    const { client } = scriptedClient([]);
    const { onTourGo } = renderAssist(client);
    fireEvent.click(screen.getByTestId("assist-open-tour"));

    expect(screen.getByTestId("tour-card")).toHaveTextContent(`Recorrido · 1 de ${TOUR_STEPS.length}`);
    expect(screen.getByTestId("tour-card")).toHaveTextContent(TOUR_STEPS[0]!.title);
    expect(screen.getByTestId("tour-prev")).toBeDisabled();

    fireEvent.click(screen.getByTestId("tour-next"));
    expect(screen.getByTestId("tour-card")).toHaveTextContent(TOUR_STEPS[1]!.title);
    expect(onTourGo).toHaveBeenLastCalledWith(TOUR_STEPS[1]);

    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(screen.getByTestId("tour-card")).toHaveTextContent(TOUR_STEPS[0]!.title);
  });

  it("termina en el último paso y se cierra con Esc", () => {
    const { client } = scriptedClient([]);
    renderAssist(client);
    fireEvent.click(screen.getByTestId("assist-open-tour"));
    for (let i = 1; i < TOUR_STEPS.length; i += 1) fireEvent.click(screen.getByTestId("tour-next"));
    expect(screen.getByTestId("tour-next")).toHaveTextContent("Terminar");
    fireEvent.click(screen.getByTestId("tour-next"));
    expect(screen.queryByTestId("tour-overlay")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("assist-open-tour"));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByTestId("tour-overlay")).not.toBeInTheDocument();
  });

  it("dice cuando la parte que describe un paso no está en pantalla", async () => {
    const { client } = scriptedClient([]);
    renderAssist(client);
    fireEvent.click(screen.getByTestId("assist-open-tour"));
    fireEvent.click(screen.getByTestId("tour-next"));
    await waitFor(() => expect(screen.getByTestId("tour-missing")).toBeInTheDocument(), { timeout: 4000 });
  });

  it("cada paso tiene título y texto, y los ids no se repiten", () => {
    expect(new Set(TOUR_STEPS.map((s) => s.id)).size).toBe(TOUR_STEPS.length);
    for (const step of TOUR_STEPS) {
      expect(step.title.trim()).not.toBe("");
      expect(step.body.length).toBeGreaterThan(0);
    }
  });

  it("placeCard pone la tarjeta bajo el elemento, sobre él si no cabe, o al centro sin elemento", () => {
    const card = { width: 348, height: 200 };
    expect(placeCard({ top: 10, left: 40, width: 200, height: 20 }, card, 1440, 900)).toEqual({ left: 40, top: 44 });
    expect(placeCard({ top: 800, left: 1300, width: 100, height: 28 }, card, 1440, 900)).toEqual({
      left: 1076,
      top: 586,
    });
    expect(placeCard(null, card, 1440, 900)).toEqual({ left: 546, top: 350 });
  });
});
