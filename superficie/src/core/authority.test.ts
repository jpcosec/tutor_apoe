import { describe, expect, it } from "vitest";
import { canEditModelContract, deduceModelOwner, resolveFieldAuthority } from "./authority";

describe("authority (L0 reglas de autoridad por modelo y dueño)", () => {
  it("deduce el dueño local, sldb-builtin y deskops", () => {
    expect(deduceModelOwner("InformeDoc", "workbench_demo.models:InformeDoc")).toBe("local");
    expect(deduceModelOwner("SpecDoc", "sldb.models.notation_models:SpecDoc")).toBe("sldb-builtin");
    expect(deduceModelOwner("TaskDoc", "deskops.models.task:TaskDoc")).toBe("deskops");
    expect(deduceModelOwner("BoardDoc")).toBe("deskops");
  });

  it("bloquea edición de source_raw, theorem y generated", () => {
    const raw = resolveFieldAuthority("FuenteDoc", "acta-comite-01", "texto", "source_raw", "workbench_demo.models:FuenteDoc");
    expect(raw.allowed).toBe(false);
    if (!raw.allowed) expect(raw.reason).toContain("source_raw");

    const thm = resolveFieldAuthority("MetricDoc", "m-01", "valor", "theorem");
    expect(thm.allowed).toBe(false);

    const gen = resolveFieldAuthority("RelationTypeDoc", "rel-1", "title", "generated", "sldb.models.relation_type_doc:RelationTypeDoc");
    expect(gen.allowed).toBe(false);
  });

  it("permite edición in-situ de modelos authored locales y bloquea los de deskops con su verbo", () => {
    const local = resolveFieldAuthority("AtomDoc", "atom-04", "cuerpo", "authored", "workbench_demo.models:AtomDoc");
    expect(local.allowed).toBe(true);
    if (local.allowed) expect(local.operation).toContain("POST /save");

    const task = resolveFieldAuthority("TaskDoc", "TaskDoc:task-01", "goal", "authored", "deskops.models:TaskDoc");
    expect(task.allowed).toBe(false);
    if (!task.allowed) {
      expect(task.suggestedVerb).toContain("deskops edit task task-01");
    }
  });

  it("solo permite editar contratos en el Studio para modelos del store local", () => {
    expect(canEditModelContract({ name: "InformeDoc", model_ref: "workbench_demo.models:InformeDoc" }).editable).toBe(true);
    expect(canEditModelContract({ name: "SpecDoc", model_ref: "sldb.models.notation_models:SpecDoc" }).editable).toBe(false);
    expect(canEditModelContract({ name: "TaskDoc", model_ref: "deskops.models:TaskDoc" }).editable).toBe(false);
  });
});
