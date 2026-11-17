import { MarkerType, Position, type Edge, type Node } from "@xyflow/react";
import { buildExploreLayoutModel, type ExploreLayoutInput } from "./explore/layoutExplore";
import { ACCENT, EDGE_STYLE, EXPLORE_DOWNSTREAM, EXPLORE_UPSTREAM, IMPACT_COLORS, JOB_COLOR, layerColor } from "./graphTheme";
import { LANE_HEADER, layoutByLayer, layoutNodes } from "./layout";
import { bundleLabel, bundleParallelEdges, DEFAULT_TRACE, nodeRole, traceSelection, type TraceRole, type TraceSettings } from "./trace";
import type { GraphPayload, Layer } from "./types";

export type NodeVisualState = "default" | "selected" | "overlay" | "dim";

/** Large graphs: with nothing selected, edges are drawn as faint context (no arrowheads/labels). */
export const CONTEXT_EDGE_THRESHOLD = 150;

export type ArchNodeData = {
  label: string;
  nodeType: string;
  layer?: string | null;
  color: string;
  complexity?: string | null;
  path?: string | null;
  summary?: string | null;
  /** Summary shown on the card itself (flow views). */
  helper?: string;
  /** Background/scheduled job metadata from the analyzer. */
  job?: { kind?: string; framework?: string; schedule?: string; command?: string };
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
  /** Heuristic (low-confidence) node: drawn dashed and labelled "inferred". */
  inferred?: boolean;
  /** Position relative to the selection's trace: upstream (depends on it) / downstream. */
  traceRole?: TraceRole;
  /** Hops from the selection along the trace (1 = direct neighbour). */
  traceHop?: number;
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
  /** Server neighbourhood ids to highlight (intersected with visible nodes; all graph views). */
  exploreNeighborIds?: Set<string> | null;
  selectedEdgeId?: string | null;
  exploreLoadingId?: string | null;
  onExploreToggle?: (id: string) => void;
  onExploreLoadMore?: (id: string) => void;
  /** Focus mode: fade nodes unrelated to the selection (default on). Off = highlight only. */
  dimUnrelated?: boolean;
  /** Multi-hop trace from the selection (direction + depth). Default: both directions, 1 hop. */
  trace?: TraceSettings;
};

export type EdgeData = {
  memberIds: string[];
  byType: Record<string, number>;
  weight: number;
  traceRole?: TraceRole;
  /** Orthogonal route from ELK (absolute canvas coordinates), when the layout computed one. */
  points?: { x: number; y: number }[];
};

const WIDTH = 216;
const BASE_HEIGHT = 78; // padding + type line + name + path (see .arch-node in styles.css)
const FIELD_HEIGHT = 18;
const HELPER_HEIGHT = 32; // two clamped lines of .arch-node-helper
const JOB_HEIGHT = 16; // .arch-node-job schedule line
const FIELDS_CHROME = 14; // divider + spacing above the field list

export type FlowBuildResult = {
  nodes: Node<ArchNodeData>[];
  edges: Edge<EdgeData>[];
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
  // Flow views print each node's summary under its name (helper text), so cards are taller.
  const helperMode = payload.view === "api-flow" || payload.view === "jobs";
  const sized = visible.map((n) => {
    const fields = fieldsByModel.get(n.id) ?? [];
    const baseH =
      BASE_HEIGHT +
      (helperMode && n.summary ? HELPER_HEIGHT : 0) +
      (n.properties?.job ? JOB_HEIGHT : 0) +
      (fields.length ? FIELDS_CHROME + (Math.min(fields.length, 12) + (fields.length > 12 ? 1 : 0)) * FIELD_HEIGHT : 0);
    const d = exploreDims?.get(n.id);
    return { id: n.id, width: d?.width ?? WIDTH, height: d?.height ?? baseH };
  });
  const layersMode = payload.view === "layers";
  // API flow focused on one endpoint: the server assigns each node a pipeline column.
  const columnsMode = payload.metadata?.layout === "columns" && Array.isArray(payload.metadata?.columns);
  const columnOrder = columnsMode ? payload.metadata!.columns!.map((c) => c.id) : [];
  const visibleById = new Map(visible.map((v) => [v.id, v]));
  const degree = new Map<string, number>();
  for (const e of visibleEdges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }
  const laneLayout = columnsMode
    ? layoutByLayer(
        sized.map((s) => {
          const p = visibleById.get(s.id)!.properties ?? {};
          // within a column: nearer the endpoint first (rank sorts descending)
          return { ...s, layer: String(p.column ?? "service"), rank: -Number(p.column_rank ?? 0) };
        }),
        { rowsPerColumn: 8, order: columnOrder, laneGap: 96 },
      )
    : layersMode
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
  // One drawn line per connected pair (imports + calls + reads fold into one with a breakdown).
  const bundled = bundleParallelEdges(drawnEdges);
  /**
   * Selection highlight (all views): a multi-hop trace over the drawn edges, split into upstream
   * (depends on the selection) and downstream (the selection depends on it). In Explore the
   * selected group's own subtree and its ancestors are never dimmed (they frame the selection).
   */
  // In the API-flow pipeline the endpoint's whole chain is the subject: selecting the endpoint
  // traces every hop instead of fading its own services and models.
  const chainRoot = columnsMode && sel && visibleById.get(sel)?.properties?.column === "endpoint";
  const traceSettings = chainRoot ? { direction: "both" as const, depth: Infinity } : (opts.trace ?? DEFAULT_TRACE);
  const trace = sel && !overlay ? traceSelection(sel, bundled, traceSettings) : null;
  let hl: Set<string> | null = null;
  if (sel && trace) {
    hl = new Set<string>([...trace.up.keys(), ...trace.down.keys()]);
    if (opts.exploreNeighborIds) {
      for (const id of opts.exploreNeighborIds) {
        if (sizeById.has(id)) hl.add(id);
      }
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
      let up = parentOfVisible.get(sel);
      while (up) {
        hl.add(up);
        up = parentOfVisible.get(up);
      }
    }
    hl.delete(sel);
  }
  const contextMode = bundled.length > CONTEXT_EDGE_THRESHOLD;
  // Labels are rendered for hover (CSS reveals them) on modest graphs, and always for the trace.
  const hoverLabels = bundled.length <= 300;
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
    let traceRole: TraceRole | undefined;
    let traceHop: number | undefined;
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
      const role = trace ? nodeRole(n.id, trace) : null;
      if (n.id === sel) {
        state = "selected";
        ring = ACCENT;
      } else if (role) {
        state = "overlay";
        ring = role === "up" ? EXPLORE_UPSTREAM : role === "down" ? EXPLORE_DOWNSTREAM : ACCENT;
        traceRole = role;
        traceHop = Math.min(trace!.up.get(n.id) ?? Infinity, trace!.down.get(n.id) ?? Infinity);
      } else if (hl.has(n.id)) {
        state = "default";
      } else if (opts.dimUnrelated !== false) {
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
        // Background/scheduled jobs get the queue/job tint whatever their layer.
        color: props.job ? JOB_COLOR : layerColor(opts.layers, n.layer),
        complexity: n.complexity,
        path: n.source_path,
        summary: n.summary,
        helper: helperMode && n.summary ? n.summary : undefined,
        job: props.job as ArchNodeData["job"],
        fanIn: Number(props.fan_in ?? 0),
        fanOut: Number(props.fan_out ?? 0),
        memberCount: props.member_count !== undefined ? Number(props.member_count) : undefined,
        fields: fieldsByModel.get(n.id),
        state,
        ring,
        badge,
        inferred: (n.confidence ?? 1) < 0.7 || Boolean(props.inferred),
        traceRole,
        traceHop,
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
    const columnLabels = new Map((payload.metadata?.columns ?? []).map((c) => [c.id, c.label]));
    for (const lane of laneLayout.lanes) {
      const name =
        columnLabels.get(lane.id) ?? opts.layers.find((l) => l.id === lane.id)?.name ?? (lane.id === "other" ? "Other" : lane.id);
      nodes.unshift({
        id: `__lane:${lane.id}`,
        type: "lane",
        position: { x: lane.x, y: 0 },
        width: lane.width,
        height: LANE_HEADER - 8,
        selectable: false,
        draggable: false,
        focusable: false,
        data: { label: name, count: lane.count, color: columnsMode ? ACCENT : layerColor(opts.layers, lane.id) } as unknown as ArchNodeData,
      });
    }
  }
  const label = (t: string) => EDGE_STYLE[t]?.label ?? t;
  const depthCache = new Map<string, number>();
  const depth = (id: string) => {
    let d = depthCache.get(id);
    if (d === undefined) {
      d = depthOf(id);
      depthCache.set(id, d);
    }
    return d;
  };
  const edges: Edge<EdgeData>[] = bundled.map((e) => {
    const style = EDGE_STYLE[e.edge_type] ?? { color: "#9A958A", label: e.edge_type };
    const weight = e.weight;
    const inOverlay = overlay?.edgeIds
      ? e.memberIds.some((id) => overlay.edgeIds!.has(id))
      : overlay
        ? overlay.ids.has(e.source) && overlay.ids.has(e.target)
        : false;
    const role = trace?.edgeRole.get(e.id);
    const edgeSelected = opts.selectedEdgeId !== undefined && opts.selectedEdgeId !== null && e.memberIds.includes(opts.selectedEdgeId);
    const emphasised = Boolean(role || edgeSelected || inOverlay);
    let opacity: number;
    if (overlay) opacity = inOverlay ? 1 : 0.15;
    else if (sel) opacity = emphasised ? 1 : opts.dimUnrelated !== false ? 0.15 : contextMode ? 0.25 : 0.5;
    else opacity = contextMode ? 0.28 : 0.7;
    const lowConfidence = (e.confidence ?? 1) < 0.7;
    const stroke =
      role === "up" ? EXPLORE_UPSTREAM : role === "down" ? EXPLORE_DOWNSTREAM : role === "both" || inOverlay ? ACCENT : style.color;
    const baseWidth = weight > 1 ? Math.min(1 + Math.log10(weight + 1) * 1.4, 4) : 1.2;
    const strokeWidth = emphasised ? Math.max(baseWidth, 2) : contextMode ? 1 : baseWidth;
    const showMarker = emphasised || !contextMode;
    const text = bundleLabel(e.byType, label) + (lowConfidence ? " · inferred" : "");
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      // Rendered for the trace / selection and (CSS-revealed on hover) on modest graphs.
      label: emphasised || hoverLabels || lowConfidence ? text : undefined,
      // Inferred (low-confidence) links keep their label visible so they are never mistaken for facts.
      className: emphasised ? "edge--hl" : lowConfidence && !contextMode ? "edge--hl edge--inferred" : contextMode && !sel ? "edge--context" : undefined,
      animated: Boolean(inOverlay),
      // Manual z-index (see ReactFlow zIndexMode): context edges sit beneath every node, the
      // trace rises above the group boxes that contain its endpoints but stays under leaf cards.
      zIndex: emphasised ? Math.max(depth(e.source), depth(e.target)) : 0,
      interactionWidth: 24,
      markerEnd: showMarker ? { type: MarkerType.ArrowClosed, color: stroke, width: 14, height: 14 } : undefined,
      labelStyle: { fill: "#5E5A51", fontSize: 10, fontWeight: 500, fontFamily: "Schibsted Grotesk Variable, Schibsted Grotesk, system-ui, sans-serif" },
      labelBgStyle: { fill: "#F7F6F2", fillOpacity: 0.95 },
      labelBgPadding: [5, 3] as [number, number],
      data: { memberIds: e.memberIds, byType: e.byType, weight, traceRole: role },
      style: {
        stroke,
        strokeWidth,
        strokeDasharray: style.dashed || lowConfidence ? "5 4" : undefined,
        opacity,
      },
    };
  });

  const exploreLayoutInput: ExploreLayoutInput | undefined = exploreMode
    ? { graphNodes: visible, graphEdges: visibleEdges }
    : undefined;

  return { nodes, edges, exploreLayoutInput };
}
