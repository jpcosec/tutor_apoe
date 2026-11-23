import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { TourStep } from "./tour-steps";

export interface TourOverlayProps {
  steps: TourStep[];
  /** Lleva la aplicación a la vista que el paso necesita. */
  onGo(step: TourStep): void;
  onClose(): void;
}

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

const CARD_WIDTH = 348;
const GAP = 14;

function boxOf(selector: string | undefined): Box | null {
  if (!selector) return null;
  const el = document.querySelector(selector);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return null;
  return { top: r.top, left: r.left, width: r.width, height: r.height };
}

/** Dónde va la tarjeta: bajo el elemento, sobre él, o dentro si ocupa casi toda la pantalla. */
export function placeCard(box: Box | null, card: { width: number; height: number }, vw: number, vh: number) {
  const clampX = (x: number) => Math.max(16, Math.min(x, vw - card.width - 16));
  const clampY = (y: number) => Math.max(16, Math.min(y, vh - card.height - 16));
  if (!box) return { left: clampX((vw - card.width) / 2), top: clampY((vh - card.height) / 2) };
  const below = box.top + box.height + GAP;
  if (below + card.height <= vh - 16) return { left: clampX(box.left), top: below };
  const above = box.top - GAP - card.height;
  if (above >= 16) return { left: clampX(box.left), top: above };
  return { left: clampX(box.left + box.width - card.width - 24), top: clampY(box.top + 24) };
}

export const TourOverlay: React.FC<TourOverlayProps> = ({ steps, onGo, onClose }) => {
  const [index, setIndex] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const [missing, setMissing] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number }>({ left: 16, top: 16 });
  const cardRef = useRef<HTMLDivElement | null>(null);
  const step = steps[index]!;
  const last = index === steps.length - 1;

  const go = useCallback(
    (next: number) => setIndex(Math.max(0, Math.min(next, steps.length - 1))),
    [steps.length],
  );

  // Al entrar a un paso: ir a su vista y buscar el elemento (la vista tarda en montarse).
  useEffect(() => {
    onGo(step);
    setMissing(false);
    setBox(null);
    if (!step.target) return;
    let tries = 0;
    let timer: number | undefined;
    const look = () => {
      const found = boxOf(step.target);
      if (found) {
        setBox(found);
        return;
      }
      tries += 1;
      if (tries > 12) setMissing(true);
      else timer = window.setTimeout(look, 150);
    };
    look();
    return () => window.clearTimeout(timer);
    // `onGo` cambia de identidad en cada render del shell; el paso es lo que manda.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  useEffect(() => {
    const refresh = () => setBox(boxOf(step.target));
    window.addEventListener("resize", refresh);
    window.addEventListener("scroll", refresh, true);
    return () => {
      window.removeEventListener("resize", refresh);
      window.removeEventListener("scroll", refresh, true);
    };
  }, [step]);

  useLayoutEffect(() => {
    const card = cardRef.current;
    const size = { width: CARD_WIDTH, height: card?.offsetHeight || 220 };
    setPos(placeCard(box, size, window.innerWidth, window.innerHeight));
  }, [box, index, missing]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        if (last) onClose();
        else go(index + 1);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        go(index - 1);
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [go, index, last, onClose]);

  useEffect(() => {
    cardRef.current?.focus();
  }, [index]);

  return (
    <div className="wb-tour" data-testid="tour-overlay">
      {box ? (
        <div
          className="wb-tour__spot"
          style={{ top: box.top - 4, left: box.left - 4, width: box.width + 8, height: box.height + 8 }}
          aria-hidden="true"
        />
      ) : (
        <div className="wb-tour__veil" aria-hidden="true" />
      )}
      <div
        ref={cardRef}
        className="wb-tour__card"
        role="dialog"
        aria-modal="false"
        aria-labelledby="wb-tour-title"
        tabIndex={-1}
        style={{ left: pos.left, top: pos.top, width: CARD_WIDTH }}
        data-testid="tour-card"
      >
        <div className="wb-tour__count">
          Recorrido · {index + 1} de {steps.length}
        </div>
        <h2 id="wb-tour-title" className="wb-tour__title">
          {step.title}
        </h2>
        {step.body.map((paragraph, i) => (
          <p key={i} className="wb-tour__body">
            {paragraph}
          </p>
        ))}
        {missing && (
          <p className="wb-tour__missing" data-testid="tour-missing">
            Esta parte no está en pantalla con el documento abierto; el paso la describe igual.
          </p>
        )}
        <div className="wb-tour__actions">
          <button type="button" className="wb-btn" onClick={onClose} data-testid="tour-close">
            Salir
          </button>
          <span className="wb-tour__spacer" />
          <button
            type="button"
            className="wb-btn"
            onClick={() => go(index - 1)}
            disabled={index === 0}
            data-testid="tour-prev"
          >
            Anterior
          </button>
          <button
            type="button"
            className="wb-btn wb-btn--primary"
            onClick={() => (last ? onClose() : go(index + 1))}
            data-testid="tour-next"
          >
            {last ? "Terminar" : "Siguiente"}
          </button>
        </div>
      </div>
    </div>
  );
};
