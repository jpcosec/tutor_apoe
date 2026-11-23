/**
 * El rechazo de SLDB al guardar, para leerlo: un título en palabras y debajo el mensaje del
 * servidor, sin traducir ni resumir (es el contrato del tipo el que habla).
 */
import React from "react";

export const AvisoGuardado: React.FC<{
  titulo: string;
  mensaje: string;
  testId?: string;
  onDismiss?: () => void;
}> = ({ titulo, mensaje, testId = "prosa-save-error", onDismiss }) => (
  <div role="alert" className="wb-aviso" data-testid={testId}>
    <strong className="wb-aviso__titulo">{titulo}</strong>
    <span className="wb-aviso__mensaje">{mensaje}</span>
    {onDismiss && (
      <button type="button" className="wb-aviso__cerrar" aria-label="Cerrar el aviso" onClick={onDismiss}>
        ×
      </button>
    )}
  </div>
);
