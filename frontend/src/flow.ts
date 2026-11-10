import { MarkerType, Position, type Edge, type Node } from "@xyflow/react";
import { buildExploreLayoutModel, type ExploreLayoutInput } from "./explore/layoutExplore";
import { ACCENT, EDGE_STYLE, EXPLORE_DOWNSTREAM, EXPLORE_UPSTREAM, IMPACT_COLORS, layerColor } from "./graphTheme";
import { LANE_HEADER, layoutByLayer, layoutNodes } from "./layout";
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
  /** Explore: expanded package/module as ELK group (title row + children). */
  exploreGroup?: boolean;
  exploreChildCount?: number;
  truncatedChildren?: number;
  exploreLoading?: boolean;
  onExploreChevronClick?: () => void;
  onExploreLoadMore?: () => void;
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
  selectedEdgeId?: string | null;
  exploreLoadingId?: string | null;
  onExploreToggle?: (id: string) => void;
  onExploreLoadMore?: (id: string) => void;
};

const WIDTH = 216;
const BASE_HEIGHT = 78; // padding + type line + name + path (see .arch-node in styles.css)
const FIELD_HEIGHT = 18;
const FIELDS_CHROME = 14; // divider + spacing above the field list

export type FlowBuildResult = {
  nodes: Node<ArchNodeData>[];
  edges: Edge[];
  /** When set, App runs nested ELK for explore */
  exploreLayoutInput?: ExploreLayoutInput;
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
  const exploreDims = exploreMode
    ? new Map(
        buildExploreLayoutModel({ graphNodes: visible, graphEdges: visibleEdges }).layoutNodes.map((ln) => [
          ln.id,
          { width: ln.width, height: ln.height },
        ]),
      )
    : null;
  const sized = visible.map((n) => {
    const fields = fieldsByModel.get(n.id) ?? [];
    const baseH = BASE_HEIGHT + (fields.length ? FIELDS_CHROME + (Math.min(fields.length, 12) + (fields.length > 12 ? 1 : 0)) * FIELD_HEIGHT : 0);
    const d = exploreDims?.get(n.id);
    return { id: n.id, width: d?.width ?? WIDTH, height: d?.height ?? baseH };
  });
  const layersMode = payload.view === "layers";
  const visibleById = new Map(visible.map((v) => [v.id, v]));
  const degree = new Map<string, number>();
  for (const e of visibleEdges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }
  const laneLayout = layersMode
    ? layoutByLayer(
        sized.map((s) => {
          const n = visibleById.get(s.id)!;
          return { ...s, layer: n.layer, rank: degree.get(s.id) ?? 0 };
        }),
        // rows grow with graph size so the whole picture stays roughly screen-shaped
        { rowsPerColumn: Math.max(8, Math.ceil(Math.sqrt(sized.length) * 1.4)) },
      )
    : null;
  const positions = exploreMode
    ? new Map(sized.map((s) => [s.id, { x: 0, y: 0 }]))
    : laneLayout
      ? laneLayout.positions
      : layoutNodes(sized, visibleEdges, "LR");
  const sizeById = new Map(sized.map((s) => [s.id, s]));

  const overlay = opts.overlay;
  // Neighbourhood dimming only makes sense when the selected node is on this canvas; otherwise
  // (e.g. its parent was collapsed) every visible node would be dimmed.
  const sel = opts.selectedId && sizeById.has(opts.selectedId) ? opts.selectedId : null;
  const parentOfVisible = new Map(
    visible.map((n) => [n.id, exploreMode ? ((n.properties?.parent_id as string | null | undefined) ?? undefined) : undefined]),
  );
  // Explore draws containment by nesting, so CONTAINS edges to a nested child are redundant clutter.
  const drawnEdges = exploreMode
    ? visibleEdges.filter((e) => !(e.edge_type === "CONTAINS" && parentOfVisible.get(e.target) === e.source))
    : visibleEdges;
  /**
   * Highlight set for the current selection (all views): direct dependency neighbours from the
   * drawn edges, plus in Explore the server neighbourhood and the selected group's own subtree
   * (a selected group must never dim its own children).
   */
  let hl: Set<string> | null = null;
  if (sel && !overlay) {
    hl = new Set<string>(exploreMode ? (opts.exploreNeighborIds ?? []) : []);
    for (const e of drawnEdges) {
      if (e.edge_type === "CONTAINS") continue;
      if (e.source === sel) hl.add(e.target);
      else if (e.target === sel) hl.add(e.source);
    }
    if (exploreMode) {
      for (const n of visible) {
        let cur = parentOfVisible.get(n.id);
        let guard = 0;
        while (cur && guard++ < 64) {
          if (cur === sel) {
            hl.add(n.id);
            break;
          }
          cur = parentOfVisible.get(cur);
        }
      }
      // keep ancestors of the selection readable too (they frame it)
      let up = parentOfVisible.get(sel);
      while (up) {
        hl.add(up);
        up = parentOfVisible.get(up);
      }
    }
    hl.delete(sel);
  }
  const showAllLabels = !sel && drawnEdges.length <= 40;
  const onToggle = opts.onExploreToggle;
  const onLoadMore = opts.onExploreLoadMore;
  const loadId = opts.exploreLoadingId ?? null;

  const depthOf = (id: string) => {
    let d = 0;
    let cur = parentOfVisible.get(id);
    while (cur && d < 64) {
      d++;
      cur = parentOfVisible.get(cur);
    }
    return d;
  };
  const ordered = exploreMode ? [...visible].sort((a, b) => depthOf(a.id) - depthOf(b.id)) : visible;
  const nodes: Node<ArchNodeData>[] = ordered.map((n) => {
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
    } else if (hl && sel) {
      if (n.id === sel) {
        state = "selected";
        ring = ACCENT;
      } else if (hl.has(n.id)) {
        state = "overlay";
        ring = "#55708F";
      } else {
        state = "dim";
      }
    }
    if (opts.selectedId === n.id) state = "selected";

    const exp = exploreMode && Boolean(props.explore_expandable);
    const nch = Number(props.child_count ?? 0);
    const parentRaw = props.parent_id as string | null | undefined;
    const parentId =
      exploreMode && parentRaw && allowed.has(parentRaw) && parentRaw !== n.id ? parentRaw : undefined;
    const truncatedChildren = exploreMode ? Number(props.truncated_children ?? 0) : 0;
    const isGroup =
      exploreMode &&
      Boolean(props.explore_expanded) &&
      (visible.some((c) => (c.properties?.parent_id as string | undefined) === n.id) || truncatedChildren > 0);

    const size = sizeById.get(n.id)!;
    return {
      id: n.id,
      type: "arch",
      position: positions.get(n.id) ?? { x: 0, y: 0 },
      width: size.width,
      height: size.height,
      parentId,
      extent: parentId ? ("parent" as const) : undefined,
      zIndex: parentId ? 1 : 0,
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      className: isGroup ? "rf-node-arch-group" : undefined,
      data: {
        // Module/package names are full paths; show the last segment (the path line keeps the rest).
        label:
          (n.node_type === "Module" || n.node_type === "Package" || n.node_type === "Migration") && n.label.includes("/")
            ? n.label.slice(n.label.lastIndexOf("/") + 1)
            : n.label,
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
        exploreExpandable: exploreMode ? exp : undefined,
        exploreExpanded: exploreMode ? Boolean(props.explore_expanded) : undefined,
        exploreGroup: exploreMode ? isGroup : undefined,
        exploreChildCount: exploreMode && exp ? nch : undefined,
        truncatedChildren: exploreMode ? truncatedChildren : undefined,
        exploreLoading: exploreMode && loadId !== null && loadId === n.id,
        onExploreChevronClick:
          exploreMode && exp && onToggle
            ? () => {
                onToggle(n.id);
              }
            : undefined,
        onExploreLoadMore:
          exploreMode && truncatedChildren > 0 && onLoadMore
            ? () => {
                onLoadMore(n.id);
              }
            : undefined,
      },
    };
  });

  if (laneLayout) {
    for (const lane of laneLayout.lanes) {
      const name = opts.layers.find((l) => l.id === lane.id)?.name ?? (lane.id === "other" ? "Other" : lane.id);
      nodes.unshift({
        id: `__lane:${lane.id}`,
        type: "lane",
        position: { x: lane.x, y: 0 },
        width: lane.width,
        height: LANE_HEADER - 8,
        selectable: false,
        draggable: false,
        focusable: false,
        data: { label: name, count: lane.count, color: layerColor(opts.layers, lane.id) } as unknown as ArchNodeData,
      });
    }
  }
  const edges: Edge[] = drawnEdges.map((e) => {
    const style = EDGE_STYLE[e.edge_type] ?? { color: "#9A958A", label: e.edge_type };
    const weight = Number(e.properties?.weight ?? 0);
    const aggregated = Boolean(e.properties?.aggregated);
    const inOverlay = overlay?.edgeIds
      ? overlay.edgeIds.has(e.id)
      : overlay
        ? overlay.ids.has(e.source) && overlay.ids.has(e.target)
        : false;
    let dim = Boolean(overlay && !inOverlay);
    let exploreRole: "upstream" | "downstream" | undefined;
    let incident = false;
    if (!overlay && hl && sel) {
      if (e.target === sel) exploreRole = "upstream";
      else if (e.source === sel) exploreRole = "downstream";
      incident = e.source === sel || e.target === sel;
      dim = !(incident || (hl.has(e.source) && hl.has(e.target)));
    }
    const lowConfidence = (e.confidence ?? 1) < 0.7;
    const strokeBase =
      exploreRole === "upstream"
        ? EXPLORE_UPSTREAM
        : exploreRole === "downstream"
          ? EXPLORE_DOWNSTREAM
          : inOverlay
            ? ACCENT
            : style.color;
    const wStroke =
      exploreMode && e.edge_type !== "CONTAINS" && weight > 1
        ? Math.min(1 + Math.log10(weight + 1) * 1.4, 4)
        : inOverlay
          ? 2
          : weight > 1
            ? Math.min(1.2 + weight * 0.2, 3.2)
            : 1.2;
    const edgeSelected = opts.selectedEdgeId === e.id;
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      // Labels only where they help: the selection's own edges, a selected edge, or small graphs.
      label:
        edgeSelected || incident || (showAllLabels && !(exploreMode && aggregated))
          ? weight > 1
            ? `${style.label} ×${weight}`
            : style.label
          : undefined,
      animated: Boolean(inOverlay),
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: strokeBase,
        width: 14,
        height: 14,
      },
      labelStyle: { fill: "#716D63", fontSize: 10, fontWeight: 500, fontFamily: "Schibsted Grotesk, system-ui, sans-serif" },
      labelBgStyle: { fill: "#F7F6F2", fillOpacity: 0.92 },
      labelBgPadding: [5, 3] as [number, number],
      style: {
        stroke: strokeBase,
        strokeWidth: incident ? Math.max(wStroke, 2) : wStroke,
        strokeDasharray: style.dashed || lowConfidence ? "5 4" : undefined,
        opacity: dim ? 0.12 : incident ? 1 : 0.7,
      },
    };
  });

  const exploreLayoutInput: ExploreLayoutInput | undefined = exploreMode
    ? { graphNodes: visible, graphEdges: visibleEdges }
    : undefined;

  return { nodes, edges, exploreLayoutInput };
}
