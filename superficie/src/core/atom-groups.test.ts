import { describe, expect, it } from "vitest";
import { groupGid, groupPayload, groupSlug, groupsFromDocuments, isAlreadyExists, isGroupGid, slugOfGroupGid, tagOfGroupGid } from "./atom-groups";

describe("slug de grupo", () => {
  it("los puntos pasan a guiones", () => {
    expect(groupSlug("riesgos")).toBe("riesgos");
    expect(groupSlug("infra.ingesta")).toBe("infra-ingesta");
    expect(groupSlug("a.b.c")).toBe("a-b-c");
  });
  it("caracteres no válidos en un nombre de documento pasan a _; conserva acentos", () => {
    expect(groupSlug("equipo de datos")).toBe("equipo_de_datos");
    expect(groupSlug("a:b/c")).toBe("a_b_c");
    expect(groupSlug("gestión.año")).toBe("gestión-año");
  });
  it("ignora puntos sobrantes", () => {
    expect(groupSlug(".infra..ingesta.")).toBe("infra-ingesta");
  });
  it("gid y reconocimiento", () => {
    expect(groupGid("infra.ingesta")).toBe("GrupoDoc:infra-ingesta");
    expect(isGroupGid("GrupoDoc:riesgos")).toBe(true);
    expect(isGroupGid("AtomDoc:a1")).toBe(false);
    expect(slugOfGroupGid("GrupoDoc:infra-ingesta")).toBe("infra-ingesta");
    expect(slugOfGroupGid("AtomDoc:a1")).toBeNull();
  });
});

describe("tag desde gid", () => {
  const known = ["infra.ingesta", "infra.almacenamiento", "riesgos", "equipo"];
  it("resuelve contra los tags conocidos y sus prefijos", () => {
    expect(tagOfGroupGid("GrupoDoc:infra-ingesta", known)).toBe("infra.ingesta");
    expect(tagOfGroupGid("GrupoDoc:infra", known)).toBe("infra");
    expect(tagOfGroupGid("GrupoDoc:riesgos", known)).toBe("riesgos");
  });
  it("sin coincidencia devuelve el slug; si no es un grupo, null", () => {
    expect(tagOfGroupGid("GrupoDoc:otro", known)).toBe("otro");
    expect(tagOfGroupGid("AtomDoc:a1", known)).toBeNull();
  });
});

describe("documentos de grupo", () => {
  it("payload y lectura", () => {
    expect(groupPayload("infra.ingesta")).toEqual({ title: "infra.ingesta", tag: "infra.ingesta", description: "" });
    const refs = groupsFromDocuments([
      { id: "riesgos", model_name: "GrupoDoc", payload: { tag: "riesgos" } },
      { id: "sin-tag", model_name: "GrupoDoc", payload: {} },
      { id: "a1", model_name: "AtomDoc", payload: {} },
    ]);
    expect(refs).toEqual([
      { id: "riesgos", gid: "GrupoDoc:riesgos", tag: "riesgos" },
      { id: "sin-tag", gid: "GrupoDoc:sin-tag", tag: "sin-tag" },
    ]);
  });
  it("409 es ya existe", () => {
    expect(isAlreadyExists({ status: 409 })).toBe(true);
    expect(isAlreadyExists({ status: 500 })).toBe(false);
    expect(isAlreadyExists(new Error("x"))).toBe(false);
    expect(isAlreadyExists(null)).toBe(false);
  });
});
