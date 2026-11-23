/**
 * El índice de la wiki (panel izquierdo de la lente Lectura): primero la configuración del tutor,
 * que se edita aquí; después el resto de la base, que se genera y solo se lee, plegado por carpeta
 * (son cientos de páginas). Los grupos y rótulos los arma `core/wiki-index`.
 */
import React from "react";
import type { WikiGroup } from "../core/wiki-index";

const Pages: React.FC<{ group: WikiGroup; activeDoc: string | null; onSelectDoc: (id: string) => void }> = ({
  group,
  activeDoc,
  onSelectDoc,
}) => (
  <ul className="wb-wiki-index__list">
    {group.pages.map((page) => {
      const active = page.id === activeDoc;
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
  </ul>
);

export const WikiIndex: React.FC<{
  groups: WikiGroup[];
  activeDoc: string | null;
  onSelectDoc: (id: string) => void;
}> = ({ groups, activeDoc, onSelectDoc }) => {
  const editable = groups.filter((g) => g.editable);
  const generated = groups.filter((g) => !g.editable);
  return (
    <nav className="wb-wiki-index" aria-label="Páginas de la wiki" data-testid="wiki-index">
      {editable.map((group) => (
        <section key={group.key} className="wb-wiki-index__group" data-testid={`wiki-group-${group.key}`}>
          <h2 className="wb-wiki-index__title">{group.label}</h2>
          <Pages group={group} activeDoc={activeDoc} onSelectDoc={onSelectDoc} />
        </section>
      ))}
      {generated.length > 0 && (
        <section className="wb-wiki-index__group" data-testid="wiki-generated">
          <h2 className="wb-wiki-index__title">La base · solo lectura</h2>
          <p className="wb-wiki-index__nota">Se genera desde los átomos fuente. Aquí se puede leer, no cambiar.</p>
          {generated.map((group) => (
            <details
              key={group.key}
              className="wb-wiki-index__fold"
              data-testid={`wiki-group-${group.key}`}
              open={group.pages.some((p) => p.id === activeDoc) || undefined}
            >
              <summary>
                {group.label} <span className="wb-wiki-index__count">{group.pages.length}</span>
              </summary>
              <Pages group={group} activeDoc={activeDoc} onSelectDoc={onSelectDoc} />
            </details>
          ))}
        </section>
      )}
    </nav>
  );
};
