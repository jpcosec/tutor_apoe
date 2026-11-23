/**
 * La ficha de una página: los campos del encabezado (precio, duración, quiénes atienden) y los
 * bloques con estructura (el horario de la semana, los colores), como controles que se leen
 * sin saber de YAML.
 *
 * No calcula ni valida: cada cambio es un `commit(path, valor)` del field, que el Workbench
 * manda a `POST /save`; el contrato del modelo lo valida SLDB y su rechazo se muestra tal cual.
 */
import React, { useEffect, useState } from "react";
import type { FieldSegment } from "../core/contract";
import type { FrontmatterRow } from "../core/layout";
import { rootOf } from "../core/paths";

const ROTULOS: Record<string, string> = {
  lun: "Lunes",
  mar: "Martes",
  mie: "Miércoles",
  jue: "Jueves",
  vie: "Viernes",
  sab: "Sábado",
  dom: "Domingo",
  duracion_min: "Duración (minutos)",
  direccion: "Dirección",
  telefono: "Teléfono",
  categoria: "Categoría",
  descripcion: "Descripción",
  atencion: "Atención",
  tipografia: "Tipografía",
  titulos: "Títulos",
  presentacion: "Presentación",
  quienes: "Quiénes lo hacen",
  cerrado: "Días cerrados",
};

/** El nombre de un campo como se le muestra a una persona: `mensajes_al_dia` → «Mensajes al dia». */
export function rotulo(clave: string): string {
  const conocido = ROTULOS[clave];
  if (conocido) return conocido;
  const texto = clave.replace(/_/g, " ").trim();
  return texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : clave;
}

export interface CampoEsquema {
  description?: string;
  kind?: string;
  enum?: unknown[];
  required?: boolean;
}

type Commit = (path: string, value: unknown) => void;

const esEscalar = (v: unknown): v is string | number | boolean | null =>
  v === null || ["string", "number", "boolean"].includes(typeof v);

/** Un texto o número que se edita en el lugar y se guarda al salir del campo o con Enter. */
const Escalar: React.FC<{
  value: string | number | null;
  numero: boolean;
  /** Un campo que acepta un número o una palabra («a cotizar»): lo que parece número viaja como número. */
  mixto?: boolean;
  canEdit: boolean;
  etiqueta: string;
  onCommit: (value: string | number) => void;
}> = ({ value, numero, mixto, canEdit, etiqueta, onCommit }) => {
  const actual = value === null ? "" : String(value);
  const [draft, setDraft] = useState(actual);
  useEffect(() => setDraft(actual), [actual]);

  if (!canEdit) return <span className="wb-ficha__valor">{actual || "—"}</span>;

  const confirmar = () => {
    const texto = draft.trim();
    if (texto === actual) return;
    if (numero) {
      if (texto === "" || Number.isNaN(Number(texto))) return setDraft(actual);
      return onCommit(Number(texto));
    }
    onCommit(mixto && /^\d+$/.test(texto) ? Number(texto) : texto);
  };

  return (
    <input
      className="wb-ficha__input"
      type={numero ? "number" : "text"}
      inputMode={numero ? "numeric" : undefined}
      aria-label={etiqueta}
      value={draft}
      placeholder="—"
      onChange={(e) => setDraft(e.target.value)}
      onBlur={confirmar}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") setDraft(actual);
      }}
    />
  );
};

/** Una lista de textos: cada elemento se quita con su ×; se agrega escribiendo y Enter. */
const Lista: React.FC<{
  items: (string | number)[];
  canEdit: boolean;
  etiqueta: string;
  vacia: string;
  onCommit: (items: (string | number)[]) => void;
}> = ({ items, canEdit, etiqueta, vacia, onCommit }) => {
  const [nuevo, setNuevo] = useState("");
  const agregar = () => {
    const texto = nuevo.trim();
    setNuevo("");
    if (texto) onCommit([...items, texto]);
  };
  return (
    <span className="wb-ficha__lista">
      {items.length === 0 && !canEdit && <span className="wb-ficha__valor wb-ficha__valor--tenue">{vacia}</span>}
      {items.map((item, i) => (
        <span key={`${item}-${i}`} className="wb-ficha__item">
          {String(item)}
          {canEdit && (
            <button
              type="button"
              className="wb-ficha__quitar"
              aria-label={`Quitar ${item} de ${etiqueta}`}
              onClick={() => onCommit(items.filter((_, j) => j !== i))}
            >
              ×
            </button>
          )}
        </span>
      ))}
      {canEdit && (
        <input
          className="wb-ficha__input wb-ficha__input--agregar"
          aria-label={`Agregar a ${etiqueta}`}
          value={nuevo}
          placeholder={items.length === 0 ? `${vacia} · escribe para agregar` : "agregar…"}
          onChange={(e) => setNuevo(e.target.value)}
          onBlur={agregar}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              agregar();
            }
          }}
        />
      )}
    </span>
  );
};

/**
 * Cualquier valor de un field, con el control que le corresponde por su forma: sí/no, número,
 * texto, opciones, lista, o un grupo de campos con nombre (que se dibuja como otra ficha).
 */
export const ValorEditable: React.FC<{
  value: unknown;
  path: string;
  etiqueta: string;
  canEdit: boolean;
  esquema?: CampoEsquema;
  kind?: string;
  onCommit: Commit;
}> = ({ value, path, etiqueta, canEdit, esquema, kind, onCommit }) => {
  const opciones = Array.isArray(esquema?.enum) ? esquema.enum.map(String) : null;

  if (typeof value === "boolean") {
    return (
      <label className="wb-ficha__sino">
        <input
          type="checkbox"
          checked={value}
          disabled={!canEdit}
          aria-label={etiqueta}
          onChange={(e) => onCommit(path, e.target.checked)}
        />
        <span>{value ? "Sí" : "No"}</span>
      </label>
    );
  }

  if (opciones && esEscalar(value)) {
    if (!canEdit) return <span className="wb-ficha__valor">{String(value ?? "—")}</span>;
    return (
      <select className="wb-ficha__input" aria-label={etiqueta} value={String(value ?? "")} onChange={(e) => onCommit(path, e.target.value)}>
        {opciones.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    );
  }

  if (Array.isArray(value)) {
    if (value.every(esEscalar)) {
      return (
        <Lista
          items={value.filter((v): v is string | number => typeof v === "string" || typeof v === "number")}
          canEdit={canEdit}
          etiqueta={etiqueta}
          vacia="ninguno"
          onCommit={(items) => onCommit(path, items)}
        />
      );
    }
    return <span className="wb-ficha__valor wb-ficha__valor--tenue">{value.length} elementos (se editan desde su origen)</span>;
  }

  if (value !== null && typeof value === "object") {
    return (
      <dl className="wb-ficha wb-ficha--anidada">
        {Object.entries(value as Record<string, unknown>).map(([clave, hijo]) => (
          <div key={clave} className="wb-ficha__fila">
            <dt>{rotulo(clave)}</dt>
            <dd>
              <ValorEditable value={hijo} path={`${path}/${clave}`} etiqueta={`${etiqueta}: ${rotulo(clave)}`} canEdit={canEdit} onCommit={onCommit} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }

  const esNumero = kind === "integer" || kind === "number" || (kind !== "unknown" && typeof value === "number");
  return (
    <Escalar
      value={value as string | number | null}
      numero={esNumero}
      mixto={kind === "unknown" || (kind === undefined && typeof value === "number")}
      canEdit={canEdit}
      etiqueta={etiqueta}
      onCommit={(v) => onCommit(path, v)}
    />
  );
};

/** El valor de un field tal como hay que editarlo: el tipado si SLDB lo entrega, si no su texto. */
export function valorDe(segment: FieldSegment): unknown {
  return segment.value !== undefined ? segment.value : segment.text;
}

/** ¿Este field tiene estructura (lista o grupo) y por eso no se edita como una línea de prosa? */
export function tieneEstructura(segment: FieldSegment): boolean {
  const valor = segment.value;
  return valor !== null && typeof valor === "object";
}

export const Ficha: React.FC<{
  rows: FrontmatterRow[];
  puedeEditar: (segment: FieldSegment) => boolean;
  esquemaDe: (path: string) => CampoEsquema | undefined;
  conFierros: boolean;
  /** El rechazo del último guardado: se muestra en la fila del campo que falló (`root`). */
  aviso?: { root: string; node: React.ReactNode } | null;
  onCommit: Commit;
}> = ({ rows, puedeEditar, esquemaDe, conFierros, aviso, onCommit }) => {
  const filas = rows
    .map((row) => ({ row, campo: row.pieces.find((p): p is { kind: "field"; segment: FieldSegment } => p.kind === "field") }))
    .filter(({ row }) => row.key !== "sldb");
  if (filas.length === 0) return null;
  return (
    <dl className="wb-ficha" data-testid="ficha">
      {filas.map(({ row, campo }) => {
        const esquema = campo ? esquemaDe(campo.segment.path) : undefined;
        return (
          <div key={row.key} className="wb-ficha__fila">
            <dt title={esquema?.description}>
              {rotulo(row.key)}
              {conFierros && campo && <span className="wb-ficha__fierro">field: {campo.segment.path}</span>}
            </dt>
            <dd>
              {campo ? (
                <ValorEditable
                  value={valorDe(campo.segment)}
                  path={campo.segment.path}
                  etiqueta={rotulo(row.key)}
                  canEdit={puedeEditar(campo.segment)}
                  esquema={esquema}
                  kind={campo.segment.kind}
                  onCommit={onCommit}
                />
              ) : (
                <span className="wb-ficha__valor">{row.pieces.map((p) => (p.kind === "text" ? p.text : "")).join("")}</span>
              )}
              {esquema?.description && <small className="wb-ficha__ayuda">{esquema.description}</small>}
              {aviso && campo && rootOf(campo.segment.path) === aviso.root && aviso.node}
            </dd>
          </div>
        );
      })}
    </dl>
  );
};
