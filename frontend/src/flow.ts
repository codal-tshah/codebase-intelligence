import { MarkerType, Position, type Edge, type Node } from "@xyflow/react";
import { ACCENT, EDGE_STYLE, IMPACT_COLORS, layerColor } from "./graphTheme";
import { layoutNodes } from "./layout";
import type { GraphPayload, Layer } from "./types";

export type NodeVisualState = "default" | "selected" | "overlay" | "dim";

export type ArchNodeData = {
  label: string;
  nodeType: string;
  layer?: string | null;
  color: string;
  complexity?: string | null;
  path?: string | null;
  summary?: string | null;
  fanIn: number;
  fanOut: number;
  memberCount?: number;
  fields?: { name: string; type: string; relation?: string }[];
  state: NodeVisualState;
  ring?: string; // overlay ring colour (impact hop / path)
  badge?: string;
  [key: string]: unknown;
};

export type Overlay = {
  ids: Set<string>;
  /** hop distance per node (0 = changed) for impact colouring */
  hops?: Map<string, number>;
  /** ordered path nodes for numbering */
  order?: string[];
  edgeIds?: Set<string>;
};

export type FlowOptions = {
  layers: Layer[];
  hiddenLayers: Set<string>;
  filter: string;
  selectedId: string | null;
  overlay: Overlay | null;
  /** Explore view: highlight neighbourhood around selection */
  exploreNeighborIds?: Set<string> | null;
};

const WIDTH = 216;
const BASE_HEIGHT = 78; // padding + type line + name + path (see .arch-node in styles.css)
const FIELD_HEIGHT = 18;
const FIELDS_CHROME = 14; // divider + spacing above the field list

export type FlowBuildResult = {
  nodes: Node<ArchNodeData>[];
  edges: Edge[];
  /** When set, App may run async ELK and apply positions */
  exploreLayoutSpec?: { sized: { id: string; width: number; height: number }[]; edges: { source: string; target: string }[] };
};

export function buildFlow(payload: GraphPayload, opts: FlowOptions): FlowBuildResult {
  const q = opts.filter.trim().toLowerCase();
  const collapseFields = payload.view === "er";

  // ER view: fold Field nodes into their model card instead of drawing hundreds of boxes.
  const fieldsByModel = new Map<string, ArchNodeData["fields"]>();
  const folded = new Set<string>();
  if (collapseFields) {
    const fieldNodes = new Map(payload.nodes.filter((n) => n.node_type === "Field").map((n) => [n.id, n]));
    for (const e of payload.edges) {
      if (e.edge_type !== "CONTAINS") continue;
      const field = fieldNodes.get(e.target);
      if (!field) continue;
      folded.add(field.id);
      const list = fieldsByModel.get(e.source) ?? [];
      const props = field.properties ?? {};
      list.push({
        name: field.label,
        type: String(props.field_type ?? ""),
        relation: props.relation_to ? String(props.relation_to) : undefined,
      });
      fieldsByModel.set(e.source, list);
    }
  }

  const visible = payload.nodes.filter((n) => {
    if (folded.has(n.id)) return false;
    if (n.layer && opts.hiddenLayers.has(n.layer)) return false;
    if (!q) return true;
    return (
      n.label.toLowerCase().includes(q) ||
      n.node_type.toLowerCase().includes(q) ||
      (n.source_path ?? "").toLowerCase().includes(q)
    );
  });
  const allowed = new Set(visible.map((n) => n.id));
  const visibleEdges = payload.edges.filter(
    (e) => allowed.has(e.source) && allowed.has(e.target) && (!collapseFields || e.edge_type !== "CONTAINS"),
  );

  const exploreMode = payload.view === "explore";
  const sized = visible.map((n) => {
    const fields = fieldsByModel.get(n.id) ?? [];
    return { id: n.id, width: WIDTH, height: BASE_HEIGHT + (fields.length ? FIELDS_CHROME + (Math.min(fields.length, 12) + (fields.length > 12 ? 1 : 0)) * FIELD_HEIGHT : 0) };
  });
  const positions = exploreMode
    ? new Map(sized.map((s) => [s.id, { x: 0, y: 0 }]))
    : layoutNodes(sized, visibleEdges, "LR");
  const sizeById = new Map(sized.map((s) => [s.id, s]));

  const overlay = opts.overlay;
  const exploreNH = opts.exploreNeighborIds;
  const nodes: Node<ArchNodeData>[] = visible.map((n) => {
    const props = n.properties ?? {};
    let state: NodeVisualState = "default";
    let ring: string | undefined;
    let badge: string | undefined;
    if (overlay) {
      if (overlay.ids.has(n.id)) {
        state = "overlay";
        const hop = overlay.hops?.get(n.id);
        if (hop !== undefined) {
          ring = IMPACT_COLORS[Math.min(hop, IMPACT_COLORS.length - 1)];
          badge = hop === 0 ? "changed" : `${hop} hop${hop > 1 ? "s" : ""}`;
        } else {
          ring = ACCENT;
          const idx = overlay.order?.indexOf(n.id) ?? -1;
          if (idx >= 0) badge = String(idx + 1);
        }
      } else {
        state = "dim";
      }
    } else if (exploreMode && exploreNH !== null && exploreNH !== undefined && opts.selectedId) {
      if (n.id === opts.selectedId) {
        state = "selected";
        ring = ACCENT;
      } else if (exploreNH.has(n.id)) {
        state = "overlay";
        ring = "#55708F";
      } else {
        state = "dim";
      }
    }
    if (opts.selectedId === n.id) state = "selected";
    if (exploreMode) {
      const exp = Boolean(props.explore_expandable);
      const nch = Number(props.child_count ?? 0);
      if (exp) {
        badge = props.explore_expanded ? "−" : nch > 0 ? `+${nch}` : "+";
      }
    }
    const size = sizeById.get(n.id)!;
    return {
      id: n.id,
      type: "arch",
      position: positions.get(n.id) ?? { x: 0, y: 0 },
      width: size.width,
      height: size.height,
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: {
        label: n.label,
        nodeType: n.node_type,
        layer: n.layer,
        color: layerColor(opts.layers, n.layer),
        complexity: n.complexity,
        path: n.source_path,
        summary: n.summary,
        fanIn: Number(props.fan_in ?? 0),
        fanOut: Number(props.fan_out ?? 0),
        memberCount: props.member_count !== undefined ? Number(props.member_count) : undefined,
        fields: fieldsByModel.get(n.id),
        state,
        ring,
        badge,
        exploreExpandable: exploreMode ? Boolean(props.explore_expandable) : undefined,
        exploreExpanded: exploreMode ? Boolean(props.explore_expanded) : undefined,
      },
    };
  });

  const edges: Edge[] = visibleEdges.map((e) => {
    const style = EDGE_STYLE[e.edge_type] ?? { color: "#9A958A", label: e.edge_type };
    const weight = Number(e.properties?.weight ?? 0);
    const inOverlay = overlay?.edgeIds
      ? overlay.edgeIds.has(e.id)
      : overlay
        ? overlay.ids.has(e.source) && overlay.ids.has(e.target)
        : false;
    let dim = Boolean(overlay && !inOverlay);
    if (!overlay && exploreMode && exploreNH !== null && exploreNH !== undefined && opts.selectedId) {
      const inc =
        e.source === opts.selectedId ||
        e.target === opts.selectedId ||
        (exploreNH.has(e.source) && exploreNH.has(e.target)) ||
        (exploreNH.has(e.source) && e.target === opts.selectedId) ||
        (e.source === opts.selectedId && exploreNH.has(e.target));
      dim = !inc;
    }
    const lowConfidence = (e.confidence ?? 1) < 0.7;
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      label: weight > 1 ? `${style.label} ×${weight}` : style.label,
      animated: Boolean(inOverlay),
      markerEnd: { type: MarkerType.ArrowClosed, color: inOverlay ? ACCENT : style.color, width: 14, height: 14 },
      labelStyle: { fill: "#716D63", fontSize: 10, fontWeight: 500, fontFamily: "Schibsted Grotesk, system-ui, sans-serif" },
      labelBgStyle: { fill: "#F7F6F2", fillOpacity: 0.92 },
      labelBgPadding: [5, 3] as [number, number],
      style: {
        stroke: inOverlay ? ACCENT : style.color,
        strokeWidth: inOverlay ? 2 : weight > 1 ? Math.min(1.2 + weight * 0.2, 3.2) : 1.2,
        strokeDasharray: style.dashed || lowConfidence ? "5 4" : undefined,
        opacity: dim ? 0.15 : 0.85,
      },
    };
  });

  const exploreLayoutSpec =
    exploreMode ? { sized, edges: visibleEdges.map((e) => ({ source: e.source, target: e.target })) } : undefined;

  return { nodes, edges, exploreLayoutSpec };
}
