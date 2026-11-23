/**
 * Una página nueva de la wiki: pide los campos obligatorios del tipo (los dice el schema del
 * store) y la crea con `POST /save` (`action: "create"`). No valida: lo que el tipo no acepta
 * lo rechaza SLDB y su mensaje se muestra tal cual. El resto de la página se completa después,
 * ya creada, en su ficha.
 */
import React, { useMemo, useState } from "react";
import type { SchemaModel } from "../core/contract";
import { newPageId, newPagePayload, planNewPage, type WikiCreatable } from "../core/wiki-index";
import { useSldb } from "../react/context";
import { AvisoGuardado } from "./AvisoGuardado";
import { rotulo } from "./Ficha";

export const NuevaPagina: React.FC<{
  tipo: WikiCreatable;
  schema: SchemaModel | undefined;
  onCreated: (id: string) => void;
  onCancel: () => void;
}> = ({ tipo, schema, onCreated, onCancel }) => {
  const { client } = useSldb();
  const plan = useMemo(() => planNewPage(schema), [schema]);
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [estado, setEstado] = useState<{ status: "idle" } | { status: "saving" } | { status: "error"; message: string }>({
    status: "idle",
  });
  const set = (name: string, value: string) => setTexts((prev) => ({ ...prev, [name]: value }));

  const crear = async (event: React.FormEvent) => {
    event.preventDefault();
    const id = newPageId(tipo.model, plan, texts);
    setEstado({ status: "saving" });
    try {
      await client.save([{ id, action: "create", model: tipo.model, payload: newPagePayload(plan, texts) }]);
      onCreated(id);
    } catch (error) {
      setEstado({ status: "error", message: error instanceof Error ? error.message : String(error) });
    }
  };

  return (
    <form className="wb-nueva" data-testid="nueva-pagina" onSubmit={(e) => void crear(e)}>
      <h1 className="wb-serif wb-nueva__titulo">Agregar {tipo.label}</h1>
      <p className="wb-nueva__ayuda">
        {plan.fields.length > 0
          ? "Escribe lo necesario para crear la página. Lo demás se completa después, en la página misma."
          : "Esta página parte con sus valores iniciales y se completa después, en la página misma."}
      </p>
      {plan.fields.map(({ field, long }) => {
        const id = `nueva-${field.name}`;
        const value = texts[field.name] ?? "";
        const opciones = Array.isArray(field.enum) ? field.enum.map(String) : null;
        return (
          <div key={field.name} className="wb-nueva__campo">
            <label htmlFor={id}>{rotulo(field.name)}</label>
            {field.kind === "boolean" ? (
              <input id={id} type="checkbox" checked={value === "true"} onChange={(e) => set(field.name, String(e.target.checked))} />
            ) : opciones ? (
              <select id={id} className="wb-nueva__input" value={value} onChange={(e) => set(field.name, e.target.value)}>
                <option value="">—</option>
                {opciones.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            ) : long ? (
              <textarea id={id} className="wb-nueva__input" rows={4} value={value} onChange={(e) => set(field.name, e.target.value)} />
            ) : (
              <input
                id={id}
                className="wb-nueva__input"
                type="text"
                inputMode={field.kind === "integer" || field.kind === "number" ? "numeric" : undefined}
                value={value}
                onChange={(e) => set(field.name, e.target.value)}
              />
            )}
            {field.description && <small className="wb-nueva__nota">{field.description}</small>}
          </div>
        );
      })}
      {estado.status === "error" && (
        <AvisoGuardado testId="nueva-pagina-error" titulo="No se pudo crear la página" mensaje={estado.message} />
      )}
      <div className="wb-nueva__acciones">
        <button type="submit" className="wb-accion wb-accion--principal" disabled={estado.status === "saving"}>
          {estado.status === "saving" ? "Creando…" : "Crear página"}
        </button>
        <button type="button" className="wb-accion" onClick={onCancel}>
          Cancelar
        </button>
      </div>
    </form>
  );
};
