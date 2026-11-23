import React, { useMemo, useState } from "react";
import { createAssistantClient } from "../core/assistant";
import type { AssistantClient, AssistantContext } from "../core/assistant";
import { AssistantDock } from "./AssistantDock";
import { TourOverlay } from "./TourOverlay";
import { TOUR_STEPS } from "./tour-steps";
import type { TourStep } from "./tour-steps";
import "./assist.css";

export interface WorkbenchAssistProps {
  context: AssistantContext;
  contextLabel: string;
  onStoreChanged(): void;
  /** Lleva la aplicación a la vista de un paso del recorrido. */
  onTourGo(step: TourStep): void;
  /** Cliente del asistente; por defecto el puente local `/assistant`. */
  assistantClient?: AssistantClient;
}

/** Esquina inferior derecha del Workbench: el recorrido guiado y el asistente. */
export const WorkbenchAssist: React.FC<WorkbenchAssistProps> = ({
  context,
  contextLabel,
  onStoreChanged,
  onTourGo,
  assistantClient,
}) => {
  const client = useMemo(() => assistantClient ?? createAssistantClient(), [assistantClient]);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [tourOpen, setTourOpen] = useState(false);

  return (
    <>
      {assistantOpen && (
        <AssistantDock
          client={client}
          context={context}
          contextLabel={contextLabel}
          onStoreChanged={onStoreChanged}
          onClose={() => setAssistantOpen(false)}
        />
      )}
      <div className="wb-assist" data-testid="workbench-assist">
        <button
          type="button"
          className="wb-assist__btn"
          onClick={() => setTourOpen(true)}
          title="Recorrido guiado: cómo se usa el Workbench"
          data-testid="assist-open-tour"
        >
          <svg viewBox="0 0 14 14" aria-hidden="true">
            <circle cx="7" cy="7" r="5.5" />
            <path d="M9.4 4.6 8 8 4.6 9.4 6 6z" />
          </svg>
          Recorrido
        </button>
        <button
          type="button"
          className="wb-assist__btn"
          onClick={() => setAssistantOpen((open) => !open)}
          aria-expanded={assistantOpen}
          title="Asistente: edita por MCP sobre lo que estás viendo"
          data-testid="assist-open-assistant"
        >
          <svg viewBox="0 0 14 14" aria-hidden="true">
            <path d="M1.8 2.5h10.4v7.2H6.2L3.4 12V9.7H1.8z" />
          </svg>
          Asistente
        </button>
      </div>
      {tourOpen && <TourOverlay steps={TOUR_STEPS} onGo={onTourGo} onClose={() => setTourOpen(false)} />}
    </>
  );
};
