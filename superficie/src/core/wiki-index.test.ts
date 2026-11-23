import { describe, expect, it } from "vitest";
import type { GraphDocument, ModelCatalogEntry, SchemaModel } from "./contract";
import { allowsMany, buildWikiIndex, configPage, humanize, isConfigModel, pageLabel, templateTitle, tutorName, typeLabel } from "./wiki-index";

const doc = (id: string, model_name: string, path: string, payload: Record<string, unknown> = {}): GraphDocument => ({
  id,
  model_name,
  path,
  payload,
});

const model = (name: string, type: string): ModelCatalogEntry => ({
  name,
  model_ref: `paginas:${name}`,
  path: "paginas.py",
  version: 1,
  canonical: false,
  family: null,
  semantics: ["representation.markdown", `type.${type}`],
  documents: 0,
});

// Las tres formas de titular una página en un template: literal, por campo, y literal más campo.
const schema: SchemaModel[] = [
  { id: "GlosarioDoc", model_ref: "p:GlosarioDoc", template: "---\nautor: ⸢rev•autor⸥\n---\n\n# Glosario\n\n⸢rev,markdown•texto⸥", fields: [{ name: "texto", kind: "string", required: true }] },
  { id: "KnowledgeAtom", model_ref: "p:KnowledgeAtom", template: "---\ntitle: ⸢rev•title⸥\n---\n\n# ⸢render•title⸥\n\n⸢rev,markdown•answer⸥", fields: [{ name: "title", kind: "string", required: true }] },
  { id: "AgentDoc", model_ref: "p:AgentDoc", template: "# Agente ⸢render•title⸥", fields: [{ name: "title", kind: "string", required: true }] },
];

describe("wiki-index · rótulos", () => {
  it("humaniza ids y tipos", () => {
    expect(humanize("core-structures")).toBe("Core structures");
    expect(typeLabel("TagNamespaceDoc")).toBe("Tag namespace");
    expect(typeLabel("AgentDoc")).toBe("Agent");
  });

  it("lee el título del template", () => {
    expect(templateTitle(schema[0]!.template)).toEqual({ literal: "Glosario", field: null });
    expect(templateTitle(schema[1]!.template)).toEqual({ literal: "", field: "title" });
    expect(templateTitle(schema[2]!.template)).toEqual({ literal: "Agente", field: "title" });
    expect(templateTitle(undefined)).toBeNull();
  });

  it("una página única se llama como su template o su tipo; una de varias, por su título", () => {
    const glosario = doc("glosario", "GlosarioDoc", "glosario.md");
    const atom = doc("atom-accion", "KnowledgeAtom", "knowledge/atom-accion.md", { title: "La Acción" });
    expect(pageLabel(glosario, false, schema[0])).toBe("Glosario");
    expect(pageLabel(doc("suelto", "KnowledgeAtom", "suelto.md"), false, schema[1])).toBe("Knowledge atom");
    expect(pageLabel(atom, true, schema[1])).toBe("La Acción");
    expect(pageLabel(doc("child_of--a--b", "RelationDoc", "relations/child_of--a--b.md"), true)).toBe("Child of a b");
    expect(pageLabel(doc("informe-1", "InformeDoc", "informe-1.md", { title: "Informe renal" }), false)).toBe("Informe renal");
    expect(allowsMany([glosario])).toBe(false);
    expect(allowsMany([atom])).toBe(true);
  });
});

// La base de un tutor: rutas, tipos y semánticas como los entrega el store de `kbs/apos`.
const kb = [
  doc("child_of", "RelationTypeDoc", "kgdb/relation_types/child_of.md", { name: "child_of" }),
  doc("atom-accion", "KnowledgeAtom", "knowledge/core-structures/action/atom-accion.md", { title: "La Acción" }),
  doc("chunk-0", "SourceChunk", "ingest/chunks/libro/chunk-0.md"),
  doc("source-libro", "SourceDoc", "ingest/sources/source-libro.md", { title: "El libro" }),
  doc("agent-tutor-apos", "AgentDoc", "agent/agent-tutor-apos.md", { title: "Tutor APOS", role: "tutor" }),
  doc("branch-apos", "BranchNode", "taxonomy/branch-apos.md", { title: "APOS" }),
];

describe("wiki-index · la base de un tutor", () => {
  it("la configuración del tutor va primero y es lo único editable; el resto, por carpeta y con su rótulo", () => {
    const groups = buildWikiIndex(kb, [model("AgentDoc", "governance.agent")], []);
    expect(groups.map((g) => [g.label, g.editable, g.pages.length])).toEqual([
      ["Configuración del tutor", true, 1],
      ["Tipos de relación", false, 1],
      ["Átomos de conocimiento", false, 1],
      ["Fuentes y fragmentos", false, 2],
      ["Ramas", false, 1],
    ]);
    expect(groups[0]!.pages).toEqual([{ id: "agent-tutor-apos", model: "AgentDoc", label: "Tutor APOS" }]);
  });

  it("una carpeta sin rótulo propio se humaniza; un tipo sin páginas no aparece", () => {
    const groups = buildWikiIndex([doc("x", "OtroDoc", "otra-carpeta/x.md")], [model("AgentDoc", "governance.agent")], []);
    expect(groups.map((g) => g.label)).toEqual(["Otra carpeta"]);
  });

  it("sin schema ni catálogo no falla: agrupa por el tipo del documento", () => {
    const groups = buildWikiIndex([doc("informe-1", "InformeDoc", "informe-1.md", { title: "Informe renal" })], []);
    expect(groups).toEqual([
      { key: "Informe", label: "Informe", pages: [{ id: "informe-1", model: "InformeDoc", label: "Informe renal" }], editable: false },
    ]);
  });

  it("el nombre del tutor y la página que se abre al entrar salen de su página de configuración", () => {
    expect(isConfigModel("AgentDoc")).toBe(true);
    expect(isConfigModel("KnowledgeAtom")).toBe(false);
    expect(configPage(kb)?.id).toBe("agent-tutor-apos");
    expect(tutorName(kb)).toBe("Tutor APOS");
    expect(tutorName(kb.filter((d) => d.model_name !== "AgentDoc"))).toBeNull();
  });
});
