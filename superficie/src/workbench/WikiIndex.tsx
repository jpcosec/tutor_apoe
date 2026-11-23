/**
 * El índice de la wiki (panel izquierdo de la lente Lectura): las páginas agrupadas por tipo,
 * la página abierta marcada y «+ Agregar» en los tipos que admiten otra página.
 * Los grupos y rótulos los arma `core/wiki-index` con lo que entrega el store.
 */
import React from "react";
import type { WikiCreatable, WikiGroup } from "../core/wiki-index";

export const WikiIndex: React.FC<{
  groups: WikiGroup[];
  activeDoc: string | null;
  /** El tipo cuya página nueva se está escribiendo, si hay una. */
  creating: string | null;
  onSelectDoc: (id: string) => void;
  onCreate: (tipo: WikiCreatable) => void;
}> = ({ groups, activeDoc, creating, onSelectDoc, onCreate }) => (
  <nav className="wb-wiki-index" aria-label="Páginas de la wiki" data-testid="wiki-index">
    {groups.map((group) => (
      <section key={group.key} className="wb-wiki-index__group" data-testid={`wiki-group-${group.key}`}>
        <h2 className="wb-wiki-index__title">{group.label}</h2>
        <ul className="wb-wiki-index__list">
          {group.pages.map((page) => {
            const active = creating === null && page.id === activeDoc;
            return (
              <li key={page.id}>
                <button
                  type="button"
                  className={`wb-wiki-index__page ${active ? "is-active" : ""}`}
                  aria-current={active ? "page" : undefined}
                  onClick={() => onSelectDoc(page.id)}
                >
                  {page.label}
                </button>
              </li>
            );
          })}
          {group.creatable.map((tipo) => (
            <li key={`nuevo-${tipo.model}`}>
              <button
                type="button"
                className={`wb-wiki-index__add ${creating === tipo.model ? "is-active" : ""}`}
                data-testid={`wiki-add-${tipo.model}`}
                onClick={() => onCreate(tipo)}
              >
                + Agregar {tipo.label}
              </button>
            </li>
          ))}
        </ul>
      </section>
    ))}
  </nav>
);
