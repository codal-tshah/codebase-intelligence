import { useEffect, useRef, type MutableRefObject } from "react";
import { flushSync } from "react-dom";
import { useReactFlow, type Edge, type Node } from "@xyflow/react";
import { buildFlow, type ArchNodeData, type EdgeData, type FlowOptions, type Overlay } from "../flow";
import type { TraceSettings } from "../trace";
import type { GraphPayload, Layer } from "../types";
import { layoutExploreGraph, routeKey, type ExploreRoutes } from "./layoutExplore";

export type ExploreFitReason = "initial" | "view" | "reset" | null;

/** Keep ELK positions/dimensions; apply latest highlight/selection styling from a fresh `buildFlow`. */
export function mergeExploreLayoutPositions(
  laidOut: Node<ArchNodeData>[],
  styled: { nodes: Node<ArchNodeData>[]; edges: Edge[] },
  routes?: ExploreRoutes,
): { nodes: Node<ArchNodeData>[]; edges: Edge[] } {
  const posById = new Map(laidOut.map((n) => [n.id, n.position]));
  const dimById = new Map(laidOut.map((n) => [n.id, { width: n.width, height: n.height }]));
  const nodes = styled.nodes.map((n) => {
    const p = posById.get(n.id);
    const d = dimById.get(n.id);
    if (!p) return n;
    return { ...n, position: p, width: d?.width ?? n.width, height: d?.height ?? n.height };
  });
  // Edges between siblings follow ELK's orthogonal route; the rest are drawn as curves.
  const edges = routes
    ? styled.edges.map((e) => {
        const points = routes.get(routeKey(e.source, e.target));
        return points ? { ...e, type: "routed", data: { ...(e.data as EdgeData), points } } : { ...e, type: "routed" };
      })
    : styled.edges;
  return { nodes, edges };
}

type Args = {
  displayed: GraphPayload | null;
  view: string;
  projectId: string;
  focusNodeId?: string;
  layers: Layer[];
  hiddenLayers: Set<string>;
  filter: string;
  overlay: Overlay | null;
  selectedId: string | null;
  /** Multi-hop trace settings for the selection. */
  trace: TraceSettings;
  selectedEdgeId: string | null;
  exploreLoadingId: string | null;
  dimUnrelated: boolean;
  onExploreToggle: (id: string) => void;
  onExploreLoadMore: (id: string) => void;
  setNodes: (nodes: Node<ArchNodeData>[]) => void;
  setEdges: (edges: Edge[]) => void;
  reducedMotion: boolean;
  /** Set by App when the user toggles a group; the camera fits that group once its layout lands. */
  lastToggleId: MutableRefObject<string | null>;
  /** Why the next Explore layout should refit the whole graph (view change / reset). */
  fitReason: MutableRefObject<ExploreFitReason>;
};

/**
 * Graph layout + camera for every view. Flat views: dagre/lane layout on each change. Explore:
 * nested ELK on structure changes only; selection, neighbourhood and edge highlights are restyled
 * on top of the last ELK result so a click never triggers a relayout or a camera jump.
 */
export function useExploreLayout(a: Args) {
  const { fitView, fitBounds } = useReactFlow();
  const laidOutRef = useRef<{ nodes: Node<ArchNodeData>[]; edges: Edge[]; gen: number; routes: ExploreRoutes } | null>(
    null,
  );
  const genRef = useRef(0);
  // Explore reads these from refs inside the structure effect so they don't trigger ELK.
  const selectedRef = useRef(a.selectedId);
  selectedRef.current = a.selectedId;
  const edgeRef = useRef(a.selectedEdgeId);
  edgeRef.current = a.selectedEdgeId;
  const traceRef = useRef(a.trace);
  traceRef.current = a.trace;

  const {
    displayed,
    view,
    layers,
    hiddenLayers,
    filter,
    overlay,
    exploreLoadingId,
    dimUnrelated,
    onExploreToggle,
    onExploreLoadMore,
    setNodes,
    setEdges,
    reducedMotion,
    lastToggleId,
    fitReason,
  } = a;

  const isExplore = Boolean(displayed && displayed.view === "explore");
  // Non-Explore views re-render on selection (cheap dagre/lane layout + highlight).
  const flatSelectedId = displayed && !isExplore ? a.selectedId : null;
  const flatTrace = displayed && !isExplore ? a.trace : undefined;
  const flatSelectedEdge = displayed && !isExplore ? a.selectedEdgeId : null;

  /** Structure + layout. In Explore, selection/neighbour highlight are read from refs. */
  useEffect(() => {
    const opts = (selectedId: string | null, tr: TraceSettings | undefined, edgeId: string | null): FlowOptions => ({
      layers,
      hiddenLayers,
      filter,
      selectedId,
      overlay,
      trace: tr,
      selectedEdgeId: edgeId,
      exploreLoadingId,
      onExploreToggle,
      onExploreLoadMore,
      dimUnrelated,
    });
    if (!displayed) {
      setNodes([]);
      setEdges([]);
      laidOutRef.current = null;
      return;
    }
    if (displayed.view !== "explore") {
      laidOutRef.current = null;
      const flow = buildFlow(displayed, opts(flatSelectedId, flatTrace, flatSelectedEdge));
      setEdges(flow.edges);
      setNodes(flow.nodes);
      return;
    }

    const flow = buildFlow(displayed, opts(selectedRef.current, traceRef.current, edgeRef.current));
    setEdges(flow.edges);
    if (!flow.exploreLayoutInput) {
      setNodes(flow.nodes);
      laidOutRef.current = null;
      return;
    }

    const layoutGen = ++genRef.current;
    const firstLayout = laidOutRef.current === null;
    let cancelled = false;
    void layoutExploreGraph(flow.exploreLayoutInput).then(({ positions: pos, routes }) => {
      if (cancelled || layoutGen !== genRef.current) return;
      const dur = reducedMotion ? 0 : 180;
      const withPos = flow.nodes.map((n) => {
        const lp = pos.get(n.id);
        if (!lp) return n;
        return { ...n, position: { x: lp.x, y: lp.y }, width: lp.width, height: lp.height };
      });
      const styledFlow = buildFlow(displayed, opts(selectedRef.current, traceRef.current, edgeRef.current));
      const merged = mergeExploreLayoutPositions(withPos, styledFlow, routes);
      laidOutRef.current = { nodes: merged.nodes, edges: merged.edges, gen: layoutGen, routes };

      flushSync(() => {
        setNodes(merged.nodes);
        setEdges(merged.edges);
      });

      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (layoutGen !== genRef.current) return;
          // While an expand/collapse is still fetching, this layout shows the *old* payload:
          // don't move the camera or consume the toggle marker yet.
          if (exploreLoadingId) return;
          const tid = lastToggleId.current;
          const reason = fitReason.current;
          const fitOpts = {
            padding: 0.18,
            duration: dur,
            minZoom: 0.05,
            maxZoom: 1.6 as number | undefined,
            nodes: merged.nodes,
            includeHiddenNodes: true,
          };
          if (reason === "view" || reason === "reset") {
            fitReason.current = null;
            void fitView(fitOpts);
          } else if (tid) {
            // Fit to the toggled group's own box (its children live inside it). Computed from the
            // layout result, not from React Flow's measurements, which lag one frame after resize.
            const byId = new Map(merged.nodes.map((x) => [x.id, x]));
            const target = byId.get(tid);
            const isGroup = merged.nodes.some((x) => x.parentId === tid);
            if (target && isGroup) {
              let x = target.position.x;
              let y = target.position.y;
              let parent = target.parentId ? byId.get(target.parentId) : undefined;
              while (parent) {
                x += parent.position.x;
                y += parent.position.y;
                parent = parent.parentId ? byId.get(parent.parentId) : undefined;
              }
              const w = Number(target.width ?? target.style?.width ?? 216);
              const h = Number(target.height ?? target.style?.height ?? 78);
              void fitBounds({ x, y, width: w, height: h }, { padding: 0.12, duration: dur });
            } else {
              // Collapsed: the graph shrank, so show the whole (smaller) picture rather than empty space.
              void fitView(fitOpts);
            }
            lastToggleId.current = null;
          } else if (firstLayout) {
            void fitView(fitOpts);
          }
          // Otherwise (selection, edge click, loading indicator, overlay) keep the camera where the user left it.
        });
      });
    });
    return () => {
      cancelled = true;
    };
  }, [
    flatSelectedId,
    flatTrace,
    flatSelectedEdge,
    displayed,
    layers,
    hiddenLayers,
    filter,
    overlay,
    exploreLoadingId,
    dimUnrelated,
    onExploreToggle,
    onExploreLoadMore,
    setNodes,
    setEdges,
    reducedMotion,
    fitView,
    fitBounds,
    lastToggleId,
    fitReason,
  ]);

  /** Explore only: update highlights when selection / neighbourhood changes — keep ELK positions. */
  useEffect(() => {
    if (view !== "explore" || !displayed || displayed.view !== "explore") return;
    const base = laidOutRef.current;
    if (!base || base.gen !== genRef.current) return;
    const flow = buildFlow(displayed, {
      layers,
      hiddenLayers,
      filter,
      selectedId: a.selectedId,
      overlay,
      trace: a.trace,
      selectedEdgeId: a.selectedEdgeId,
      exploreLoadingId,
      onExploreToggle,
      onExploreLoadMore,
      dimUnrelated,
    });
    const merged = mergeExploreLayoutPositions(base.nodes, flow, base.routes);
    laidOutRef.current = { ...merged, gen: base.gen, routes: base.routes };
    setNodes(merged.nodes);
    setEdges(merged.edges);
  }, [
    view,
    displayed,
    layers,
    hiddenLayers,
    filter,
    a.selectedId,
    overlay,
    a.trace,
    a.selectedEdgeId,
    exploreLoadingId,
    dimUnrelated,
    onExploreToggle,
    onExploreLoadMore,
    setNodes,
    setEdges,
  ]);

  /** Flat views: fit the whole diagram when the structure (not the selection) changes. */
  const layoutSig = `${a.projectId}|${displayed?.view}|${a.focusNodeId}|${displayed?.nodes.length}|${hiddenLayers.size}|${filter}`;
  useEffect(() => {
    if (view === "explore") return;
    const dur = reducedMotion ? 0 : 300;
    const t = setTimeout(() => void fitView({ padding: 0.15, duration: dur }), 60);
    return () => clearTimeout(t);
  }, [layoutSig, fitView, reducedMotion, view]);
}
