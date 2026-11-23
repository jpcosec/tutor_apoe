import { describe, expect, it } from "vitest";
import { isolatedDocuments, parseNode } from "./graph-nodes";

describe("parseNode", () => {
  it("parte un documento en modelo e id, y lo deja enlazable", () => {
    const node = parseNode("sldb://document/ConversationStep:step-cobranza-respuesta");
    expect(node).toMatchObject({ kind: "document", model: "ConversationStep", doc: "step-cobranza-respuesta", label: "step-cobranza-respuesta" });
  });

  it("un id con dos puntos adentro conserva todo lo que sigue al primer corte", () => {
    const node = parseNode("sldb://document/RelationDoc:grounded_by--TemplateDoc:template-x--DomainAtom:domain-y");
    expect(node.model).toBe("RelationDoc");
    expect(node.doc).toBe("grounded_by--TemplateDoc:template-x--DomainAtom:domain-y");
  });

  it("un field no es enlazable: no tiene documento que abrir", () => {
    const node = parseNode("sldb://field/AgentFraming.framing");
    expect(node.kind).toBe("field");
    expect(node.model).toBe("AgentFraming");
    expect(node.doc).toBeUndefined();
  });

  it("una URI que no matcha el esquema se devuelve cruda, sin inventar partes", () => {
    const node = parseNode("no-es-una-uri");
    expect(node).toEqual({ uri: "no-es-una-uri", kind: "unknown", label: "no-es-una-uri" });
  });
});

describe("isolatedDocuments", () => {
  it("descarta los nodos de tipo field y deja solo documentos", () => {
    const docs = isolatedDocuments([
      "sldb://document/FallbackRule:fallback-cobranza",
      "sldb://field/AgentFraming.examples",
      "sldb://field/AgentFraming.id",
      "sldb://document/SelfDeclaration:self-antonia-cobranza",
    ]);
    expect(docs.map((node) => node.doc)).toEqual(["fallback-cobranza", "self-antonia-cobranza"]);
  });
});
