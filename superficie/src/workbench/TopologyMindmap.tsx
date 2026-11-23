import React, { useCallback, useMemo } from "react";
import type {
  DocumentSegments,
  Edge,
  GraphDocument,
  ModelDescription,
} from "../core/contract";

export interface MindmapChildNode {
  key: string;
  slotLabel: string;
  modelLabel: string;
  title: string;
  refTarget: string;
  docId: string;
  kind: "atom" | "spec" | "source" | "doc";
}

export interface TopologyMindmapProps {
  data: DocumentSegments;
  documents: GraphDocument[];
  edges: Edge[];
  modelDetail: ModelDescription | null;
  hoveredRefDoc: string | null;
  onSelectDoc: (docId: string) => void;
  onInspectDiagram: (specId: string) => void;
  onOpenSource: (sourceDocId: string) => void;
  onOpenStudio: (modelName: string) => void;
}

function parseRefString(raw: string): { model: string | null; docId: string; field: string | null } | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const typed = /^([A-Z][A-Za-z0-9_]*Doc):([a-zA-Z0-9_.-]+)(?:#([a-zA-Z0-9_./-]+))?$/.exec(trimmed);
  if (typed) {
    return { model: typed[1]!, docId: typed[2]!, field: typed[3] ?? null };
  }
  const docsPath = /^docs\/(?:([A-Z][A-Za-z0-9_]*Doc)\/)?([a-zA-Z0-9_.-]+)(?:\/([a-zA-Z0-9_.-]+))?(?:\.md)?$/.exec(
    trimmed,
  );
  if (docsPath) {
    return { model: docsPath[1] ?? null, docId: docsPath[2]!, field: docsPath[3] ?? null };
  }
  return null;
}

export const TopologyMindmap: React.FC<TopologyMindmapProps> = ({
  data,
  documents,
  edges,
  modelDetail,
  hoveredRefDoc,
  onSelectDoc,
  onInspectDiagram,
  onOpenSource,
  onOpenStudio,
}) => {
  /** `endpoint` de una arista (`Model:name` o `name`) es el documento activo. */
  const isActiveEndpoint = useCallback(
    (endpoint: string) => endpoint === data.id || endpoint === data.doc || endpoint.endsWith(`:${data.doc}`),
    [data.id, data.doc],
  );

  // 1. Fuente upstream: declarada en el payload o arista real hacia una FuenteDoc
  const upstreamSource = useMemo(() => {
    const payload = data.payload ?? {};
    for (const key of ["fuente_ref", "source", "fuente", "acta"]) {
      const val = payload[key];
      if (typeof val === "string" && val.trim()) {
        const parsed = parseRefString(val) ?? {
          model: val.includes(":") ? val.split(":")[0]! : null,
          docId: val.includes(":") ? val.split(":")[1]! : val,
          field: null,
        };
        const found = documents.find(
          (d) => d.id === parsed.docId || d.id.endsWith(`:${parsed.docId}`),
        );
        return {
          docId: parsed.docId,
          model: found?.model_name ?? parsed.model ?? "",
          title: String(found?.payload?.title ?? parsed.docId),
        };
      }
    }
    // Sin declaración en el payload: solo una arista real del documento hacia una FuenteDoc.
    const toSource = edges.find(
      (e) => isActiveEndpoint(e.source) && e.target.toLowerCase().startsWith("fuente"),
    );
    if (toSource) {
      const [model, name] = toSource.target.includes(":")
        ? [toSource.target.split(":")[0]!, toSource.target.split(":")[1]!]
        : ["", toSource.target];
      const found = documents.find((d) => d.id === name || d.id === toSource.target);
      return {
        docId: name,
        model: found?.model_name ?? model,
        title: String(found?.payload?.title ?? name),
      };
    }
    return null;
  }, [data.payload, documents, edges, isActiveEndpoint]);

  // 2. Discover child nodes from segments & payload fields
  const childNodes = useMemo(() => {
    const list: MindmapChildNode[] = [];
    const seen = new Set<string>();

    const addChild = (
      slotLabel: string,
      modelLabel: string,
      docId: string,
      field: string | null,
      kind: MindmapChildNode["kind"],
      fallbackTitle?: string,
    ) => {
      if (!docId || docId === data.doc || seen.has(`${slotLabel}:${docId}`)) return;
      seen.add(`${slotLabel}:${docId}`);
      const targetDoc = documents.find(
        (d) => d.id === docId || d.id.endsWith(`:${docId}`),
      );
      const resolvedModel = targetDoc?.model_name ?? modelLabel;
      const resolvedKind: MindmapChildNode["kind"] =
        kind !== "doc"
          ? kind
          : resolvedModel === "SpecDoc"
            ? "spec"
            : resolvedModel === "FuenteDoc" || resolvedModel === "ActaDoc"
              ? "source"
              : resolvedModel === "AtomDoc"
                ? "atom"
                : "doc";
      const title = String(
        targetDoc?.payload?.title ?? fallbackTitle ?? docId,
      );
      list.push({
        key: `${slotLabel}:${docId}`,
        slotLabel,
        modelLabel: resolvedModel === "SpecDoc" ? "Spec2Viz" : resolvedModel,
        title,
        refTarget: field ? `${docId}#${field}` : docId,
        docId,
        kind: resolvedKind,
      });
    };

    for (const seg of data.segments) {
      if (seg.type === "composition") {
        const cleanId = seg.source.doc
          ? seg.source.doc.includes(":")
            ? seg.source.doc.split(":")[1]!
            : seg.source.doc
          : "";
        const parsedRef = parseRefString(seg.ref);
        const docId = cleanId || parsedRef?.docId || "";
        const field = parsedRef?.field ?? (seg.source.path || null);
        addChild(
          `.${seg.path}[${seg.ref_index}]`,
          seg.source.model || parsedRef?.model || "",
          docId,
          field,
          "doc",
        );
      } else if (seg.type === "field") {
        if (seg.projection) {
          const specRaw = seg.projection.spec || String(seg.value ?? "");
          const cleanSpec = specRaw.includes(":") ? specRaw.split(":")[1]! : specRaw;
          addChild(
            `.${seg.path}`,
            "Spec2Viz",
            cleanSpec,
            null,
            "spec",
            seg.projection.title,
          );
        }
        for (const child of seg.children ?? []) {
          if (child.type === "composition") {
            const cleanId = child.source.doc
              ? child.source.doc.includes(":")
                ? child.source.doc.split(":")[1]!
                : child.source.doc
              : "";
            const parsedRef = parseRefString(child.ref);
            const docId = cleanId || parsedRef?.docId || "";
            const field = parsedRef?.field ?? (child.source.path || null);
            addChild(
              `.${seg.path}[${child.ref_index}]`,
              child.source.model || parsedRef?.model || "",
              docId,
              field,
              "doc",
            );
          }
        }
      }
    }

    // Also inspect payload arrays/strings for references not expanded as composition segments
    for (const [key, val] of Object.entries(data.payload ?? {})) {
      if (key === "fuente_ref" || key === "source") continue;
      if (typeof val === "string") {
        const parsed = parseRefString(val);
        if (parsed) {
          addChild(`.${key}`, parsed.model ?? "", parsed.docId, parsed.field, "doc");
        }
      } else if (Array.isArray(val)) {
        val.forEach((item, idx) => {
          if (typeof item === "string") {
            const parsed = parseRefString(item);
            if (parsed) {
              addChild(
                `.${key}[${idx}]`,
                parsed.model ?? "",
                parsed.docId,
                parsed.field,
                "doc",
              );
            }
          }
        });
      }
    }

    return list;
  }, [data.segments, data.payload, data.doc, documents]);

  const rootTitle = String(data.payload?.title ?? data.doc);
  const declaredVersion = data.payload?.version;
  const versionStr =
    typeof declaredVersion === "string" || typeof declaredVersion === "number" ? String(declaredVersion) : null;

  const backlinkCount = useMemo(
    () => edges.filter((e) => isActiveEndpoint(e.target) && !isActiveEndpoint(e.source)).length,
    [edges, isActiveEndpoint],
  );

  const handleClickNode = (node: MindmapChildNode) => {
    if (node.kind === "spec") {
      onInspectDiagram(node.docId);
    } else if (node.kind === "source") {
      onOpenSource(node.docId);
    } else {
      onSelectDoc(node.docId);
    }
  };

  // Dynamic positions for right-hand children (y coordinates)
  const rootY = 185;
  const childPositions = childNodes.map((_, idx) => {
    const spacing = 74;
    const totalHeight = Math.max(0, (childNodes.length - 1) * spacing);
    const startY = Math.max(76, rootY - totalHeight / 2);
    return startY + idx * spacing;
  });

  return (
    <section
      className="wb-pane-left-38"
      aria-label="Topología Espacial del Documento"
      data-testid="topology-mindmap-pane"
    >
      {/* 2D Spatial Mindmap Canvas with SVG Bézier Curves */}
      <div data-testid="topology-mindmap" style={{ flex: 1, position: "relative", overflow: "auto", minHeight: 320 }}>
        <svg
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            pointerEvents: "none",
            zIndex: 0,
          }}
        >
          {/* Dashed curve from Upstream Source to ROOT */}
          {upstreamSource && (
            <path
              d={`M 68 88 C 68 158, 52 ${rootY + 12}, 96 ${rootY + 12}`}
              fill="none"
              stroke="#D4D2CC"
              strokeDasharray="2 2"
              strokeWidth="1"
            />
          )}

          {/* Solid Bézier curves from ROOT right edge to each Child */}
          {childPositions.map((cy, idx) => (
            <path
              key={childNodes[idx]?.key ?? idx}
              d={`M 252 ${rootY + 12} C 284 ${rootY + 12}, 284 ${cy + 22}, 308 ${cy + 22}`}
              fill="none"
              stroke={
                hoveredRefDoc === childNodes[idx]?.docId ? "#1A1A1A" : "#D4D2CC"
              }
              strokeWidth={hoveredRefDoc === childNodes[idx]?.docId ? "1.4" : "1"}
            />
          ))}
        </svg>

        {/* Upstream Source Node (top-left) */}
        {upstreamSource && (
          <div
            style={{ position: "absolute", left: 20, top: 44, zIndex: 10, cursor: "pointer" }}
            onClick={() => onOpenSource(upstreamSource.docId)}
            title={`Abrir fuente primaria ${upstreamSource.docId}`}
          >
            <div
              className="wb-mono"
              style={{
                fontSize: 9,
                color: "var(--wb-ink-muted)",
                marginBottom: 2,
                display: "flex",
                gap: 4,
              }}
            >
              <span>← fuente</span>
              {upstreamSource.model && (
                <span style={{ color: "var(--wb-ink-tertiary)" }}>· {upstreamSource.model}</span>
              )}
            </div>
            <div
              style={{
                backgroundColor: "var(--wb-paper)",
                border: "1px solid var(--wb-border)",
                padding: "4px 10px",
                borderRadius: "var(--wb-radius)",
              }}
            >
              <span
                className="wb-serif"
                style={{ fontSize: 12, color: "var(--wb-ink-body)", display: "block" }}
              >
                {upstreamSource.title}
              </span>
            </div>
          </div>
        )}

        {/* Center ROOT Document Node */}
        <div
          style={{
            position: "absolute",
            left: 84,
            top: rootY - 16,
            width: 168,
            zIndex: 20,
          }}
        >
          <div
            className="wb-mono"
            style={{
              fontSize: 9,
              color: "var(--wb-ink-muted)",
              marginBottom: 4,
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span
              style={{
                fontSize: 8,
                padding: "1px 4px",
                backgroundColor: "var(--wb-ink)",
                color: "var(--wb-paper)",
                borderRadius: "var(--wb-radius)",
              }}
            >
              ROOT
            </span>
            <span>class {data.model}</span>
          </div>
          <div
            style={{
              backgroundColor: "var(--wb-paper)",
              border: "1px solid var(--wb-ink)",
              borderRadius: "var(--wb-radius)",
              padding: "8px 12px",
            }}
          >
            <span
              className="wb-serif"
              style={{
                fontSize: 12.5,
                fontWeight: 600,
                color: "var(--wb-ink)",
                display: "block",
              }}
            >
              {rootTitle}
            </span>
            <span
              className="wb-mono"
              style={{
                fontSize: 9.5,
                color: "var(--wb-ink-muted)",
                display: "block",
                marginTop: 2,
              }}
            >
              id: {data.doc}
            </span>
          </div>
        </div>

        {/* Right Child Nodes (.criterios[0], .reglas[0], .diagrama_flujo) */}
        {childNodes.map((child, idx) => {
          const top = childPositions[idx] ?? 80;
          const isHovered = hoveredRefDoc === child.docId;
          return (
            <div
              key={child.key}
              style={{
                position: "absolute",
                left: 308,
                right: 16,
                top,
                zIndex: 10,
                cursor: "pointer",
              }}
              onClick={() => handleClickNode(child)}
            >
              <div
                className="wb-mono"
                style={{
                  fontSize: 9,
                  color: "var(--wb-ink-muted)",
                  marginBottom: 2,
                  display: "flex",
                  gap: 4,
                }}
              >
                <span>{child.slotLabel}</span>
                {child.modelLabel && (
                  <span style={{ color: "var(--wb-ink-tertiary)" }}>· {child.modelLabel}</span>
                )}
              </div>
              <div
                style={{
                  backgroundColor: "var(--wb-paper)",
                  border: `1px solid ${isHovered ? "var(--wb-ink)" : "var(--wb-border)"}`,
                  borderRadius: "var(--wb-radius)",
                  padding: "5px 10px",
                }}
              >
                <span
                  style={{
                    fontSize: 11.5,
                    color: "var(--wb-ink-body)",
                    display: "block",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {child.title}
                </span>
                <span
                  className="wb-mono"
                  style={{
                    fontSize: 9,
                    color: "var(--wb-ink-tertiary)",
                    display: "block",
                  }}
                >
                  {child.refTarget}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Bottom Schema Summary Drawer (schema: InformeDoc) */}
      <div
        style={{
          padding: "14px 16px",
          borderTop: "1px solid var(--wb-hairline)",
          backgroundColor: "var(--wb-paper)",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            paddingBottom: 6,
            marginBottom: 8,
            borderBottom: "1px solid var(--wb-hairline)",
            cursor: "pointer",
          }}
          onClick={() => onOpenStudio(data.model)}
          title="Abrir contrato de modelo en Esquema Studio"
        >
          <div className="wb-mono" style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 500, color: "var(--wb-ink)" }}>
              schema: {data.model}
            </span>
            {versionStr && (
              <span style={{ fontSize: 10, color: "var(--wb-ink-muted)" }}>({versionStr})</span>
            )}
          </div>
          <span className="wb-mono" style={{ fontSize: 10, color: "var(--wb-ink-muted)" }}>
            ↗
          </span>
        </div>

        <div
          className="wb-mono"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 5,
            fontSize: 10,
            color: "var(--wb-ink-muted)",
          }}
        >
          {(modelDetail?.fields ?? []).map((f) => {
            const comp = modelDetail?.compositions?.[f.name];
            const target = comp?.model
              ? `${comp.model}${comp.source_field ? `#${comp.source_field}` : ""}`
              : null;
            const rhs = comp ? (target ? `list[Ref[${target}]]` : f.annotation) : f.annotation;
            return (
              <div
                key={f.name}
                style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
              >
                <span style={{ color: "var(--wb-ink-body)" }}>{f.name}:</span>
                <span>{rhs}</span>
              </div>
            );
          })}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              paddingTop: 5,
              marginTop: 2,
              borderTop: "1px solid var(--wb-hairline)",
              fontSize: 9,
              color: "var(--wb-ink-tertiary)",
            }}
          >
            <span>backlinks:</span>
            <span>list[NodeRef] ({backlinkCount} links)</span>
          </div>
        </div>
      </div>
    </section>
  );
};
