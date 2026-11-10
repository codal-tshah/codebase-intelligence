import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { flushSync } from "react-dom";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  ArrowLeft,
  BookOpen,
  Check,
  ChevronsLeft,
  Download,
  Filter,
  GitFork,
  Link as LinkIcon,
  MessageSquare,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  RefreshCw,
  Route as RouteIcon,
  Search,
  X,
} from "lucide-react";
import { API, getJson, postJson } from "./api";
import { ArchNode, LaneLabel } from "./components/ArchNode";
import { ChatPanel } from "./components/ChatPanel";
import { CommandPalette, type PaletteAction } from "./components/CommandPalette";
import { EndpointsPanel } from "./components/EndpointsPanel";
import { FreshnessBanner } from "./components/FreshnessBanner";
import { ImpactPanel } from "./components/ImpactPanel";
import { IngestPanel } from "./components/IngestPanel";
import { Inspector } from "./components/Inspector";
import { LayerLegend } from "./components/LayerLegend";
import { PathPanel } from "./components/PathPanel";
import { ProjectSummaryCard, type ProjectSummary } from "./components/ProjectSummaryCard";
import { TourPanel } from "./components/TourPanel";
import { buildFlow, type ArchNodeData, type Overlay } from "./flow";
import { ExploreGraphCache, exploreCacheKey } from "./explore/exploreGraphCache";
import { decodeExpandedIds, encodeExpandedIds } from "./explore/hash";
import { layoutExploreNodes } from "./explore/layoutExplore";
import { createExploreState, exploreReducer } from "./explore/useExploreState";
import { DEFAULT_LAYERS, VIEW_META } from "./graphTheme";
import { ViewIcon } from "./icons";
import type {
  EndpointInfo,
  Freshness,
  GraphPayload,
  UnderlyingEdgesPayload,
  ImpactReport,
  NeighborhoodPayload,
  Job,
  Layer,
  GraphEdge,
  NodeDetail,
  PathResult,
  Project,
  SearchHit,
  SourceSnippet,
  TourStep,
  ViewInfo,
} from "./types";

const NODE_TYPES = { arch: ArchNode, lane: LaneLabel };

type RightTab = "inspector" | "endpoints" | "tour" | "impact" | "path" | "assistant";
/** Primary tabs first; analysis tools are quieter and also reachable from ⌘K and node actions. */
const TABS: { id: RightTab; label: string; secondary?: boolean }[] = [
  { id: "inspector", label: "Details" },
  { id: "endpoints", label: "Routes" },
  { id: "assistant", label: "Ask" },
  { id: "tour", label: "Tour", secondary: true },
  { id: "impact", label: "Impact", secondary: true },
  { id: "path", label: "Path", secondary: true },
];

function readPref<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

function writePref(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable (private mode) */
  }
}

/** Fallback catalog until the API answers (and for older servers without /views). */
const FALLBACK_VIEWS: ViewInfo[] = Object.entries(VIEW_META).map(([id, m]) => ({
  id,
  label: m.label,
  description: m.description,
  icon: m.icon,
  group: "explore",
  focusable: id === "api-flow" || id === "call-graph" || id === "components",
  best_for: [],
  available: true,
  count: null,
}));

const FALLBACK_BEST: Record<string, string> = {
  Endpoint: "api-flow",
  Function: "call-graph",
  Class: "call-graph",
  Middleware: "call-graph",
  Component: "components",
  Model: "er",
  Field: "er",
  Package: "explore",
  ExternalService: "integrations",
};

// ------------------------------------------------------------------ deep links

type HashState = { p?: string; v?: string; n?: string; f?: string; e?: string };

function readHash(): HashState {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const params = new URLSearchParams(raw);
  return {
    p: params.get("p") ?? undefined,
    v: params.get("v") ?? undefined,
    n: params.get("n") ?? undefined,
    f: params.get("f") ?? undefined,
    e: params.get("e") ?? undefined,
  };
}

function writeHash(state: HashState) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(state)) if (v) params.set(k, v);
  const next = `#/${params.toString()}`;
  if (window.location.hash !== next) window.history.replaceState(null, "", next);
}

/** Keep ELK positions/dimensions; apply latest highlight/selection styling from a fresh `buildFlow`. */
function mergeExploreLayoutPositions(
  laidOut: Node<ArchNodeData>[],
  styled: { nodes: Node<ArchNodeData>[]; edges: Edge[] },
): { nodes: Node<ArchNodeData>[]; edges: Edge[] } {
  const posById = new Map(laidOut.map((n) => [n.id, n.position]));
  const dimById = new Map(
    laidOut.map((n) => [n.id, { width: n.width as number | undefined, height: n.height as number | undefined }]),
  );
  const nodes = styled.nodes.map((n) => {
    const p = posById.get(n.id);
    const d = dimById.get(n.id);
    if (!p) return n;
    return { ...n, position: p, width: d?.width ?? n.width, height: d?.height ?? n.height };
  });
  return { nodes, edges: styled.edges };
}

// ---------------------------------------------------------------- overlays

function impactToPayload(r: ImpactReport): GraphPayload {
  const items = [...r.changed.filter((c) => c.node_type !== "Field").map((c) => ({ ...c, hops: 0 })), ...r.affected];
  const seen = new Set<string>();
  const nodes = [];
  for (const it of items) {
    if (seen.has(it.id) || nodes.length >= 90) continue;
    seen.add(it.id);
    nodes.push({
      id: it.id,
      label: it.name,
      node_type: it.node_type,
      source_path: it.source_path,
      layer: it.layer,
      complexity: it.complexity,
    });
  }
  return { view: "impact", nodes, edges: r.edges.filter((e) => seen.has(e.source) && seen.has(e.target)) };
}

function pathToPayload(r: PathResult): GraphPayload {
  return {
    view: "path",
    nodes: r.nodes.map((n) => ({ id: n.id, label: n.name, node_type: n.node_type, source_path: n.source_path, layer: n.layer })),
    edges: r.edges,
  };
}

function Dashboard() {
  const { fitView, fitBounds, getNodes } = useReactFlow();
  const initialHash = useRef<HashState>(readHash());
  const viewChosenRef = useRef<boolean>(Boolean(initialHash.current.v));
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [layers, setLayers] = useState<Layer[]>(DEFAULT_LAYERS);
  const [views, setViews] = useState<ViewInfo[]>(FALLBACK_VIEWS);
  const [view, setView] = useState(initialHash.current.v ?? "layers");
  const [focusNodeId, setFocusNodeId] = useState<string | undefined>(initialHash.current.f);
  const [payload, setPayload] = useState<GraphPayload | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [exploreState, exploreDispatch] = useReducer(
    exploreReducer,
    initialHash.current.e ? decodeExpandedIds(initialHash.current.e) : [],
    (expandedFromHash) => createExploreState(expandedFromHash),
  );
  const exploreExpanded = exploreState.expanded;
  const exploreChildOffsets = exploreState.childOffsets;
  const [exploreNeighborIds, setExploreNeighborIds] = useState<Set<string> | null>(null);
  const [exploreLoadingId, setExploreLoadingId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [exploreEdgeDetail, setExploreEdgeDetail] = useState<{
    edge: GraphEdge;
    underlying: UnderlyingEdgesPayload | null;
    loading: boolean;
  } | null>(null);
  const exploreGraphCache = useRef(new ExploreGraphCache(20));
  const explorePrevPos = useRef<Map<string, { x: number; y: number }>>(new Map());
  const exploreLaidOutFlowRef = useRef<{ nodes: Node<ArchNodeData>[]; edges: Edge[]; gen: number } | null>(null);
  const exploreLayoutGenRef = useRef(0);
  const exploreSelectedIdRef = useRef<string | null>(null);
  exploreSelectedIdRef.current = selectedId;
  const exploreClickTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const exploreLastToggleId = useRef<string | null>(null);
  const exploreFitReason = useRef<"initial" | "view" | "reset" | null>(null);
  const [focusDepth, setFocusDepth] = useState(1);
  const [detail, setDetail] = useState<NodeDetail | null>(null);
  const [source, setSource] = useState<SourceSnippet | null>(null);
  const [highlight, setHighlight] = useState<[number, number] | null>(null);

  const [filter, setFilter] = useState("");
  const [hiddenLayers, setHiddenLayers] = useState<Set<string>>(new Set());
  const [rightTab, setRightTab] = useState<RightTab>("inspector");

  const [tourStep, setTourStep] = useState<number | null>(null);
  const [tourIds, setTourIds] = useState<string[]>([]);
  const [chatIds, setChatIds] = useState<string[]>([]);
  const [chatSeed, setChatSeed] = useState<{ text: string; token: number } | null>(null);
  const [impact, setImpact] = useState<ImpactReport | null>(null);
  const [impactToken, setImpactToken] = useState(0);
  const [pathResult, setPathResult] = useState<PathResult | null>(null);

  const [summary, setSummary] = useState<ProjectSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [freshness, setFreshness] = useState<Freshness | null>(null);
  const [reindexing, setReindexing] = useState(false);

  const [ingestBusy, setIngestBusy] = useState(false);
  const [ingestError, setIngestError] = useState<string | null>(null);
  const [showIngest, setShowIngest] = useState(false);
  const [copied, setCopied] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState<boolean>(() => readPref("ci.panel.open", true));
  const [panelWidth, setPanelWidth] = useState<number>(() => readPref("ci.panel.width", 380));
  useEffect(() => writePref("ci.panel.open", panelOpen), [panelOpen]);
  useEffect(() => writePref("ci.panel.width", panelWidth), [panelWidth]);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<ArchNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  const activeProject = projects.find((p) => p.id === projectId);
  const currentView = views.find((v) => v.id === view);

  // ---- bootstrap -----------------------------------------------------------------------------
  useEffect(() => {
    getJson<Layer[]>("/layers").then(setLayers).catch(() => undefined);
    getJson<Project[]>("/projects")
      .then((data) => {
        setProjects(data);
        const wanted = initialHash.current.p;
        const pick = data.find((p) => p.id === wanted) ?? data[0];
        if (pick) setProjectId(pick.id);
        setShowIngest(data.length === 0);
      })
      .catch(() => setShowIngest(true));
  }, []);

  const loadSummary = useCallback(async (id: string) => {
    setSummaryLoading(true);
    try {
      const s = await getJson<ProjectSummary>(`/projects/${id}/summary`);
      setSummary(s);
      // Large graph: default to Explore, but never override a view the user picked
      // (sidebar click or a deep link with v=...).
      if (s.preferExploreView && !viewChosenRef.current) {
        setView((v) => (v === "layers" ? "explore" : v));
      }
    } catch {
      setSummary(null);
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  const loadFreshness = useCallback(async (id: string) => {
    try {
      setFreshness(await getJson<Freshness>(`/projects/${id}/freshness`));
    } catch {
      setFreshness(null);
    }
  }, []);

  useEffect(() => {
    if (!projectId) return;
    void loadSummary(projectId);
    void loadFreshness(projectId);
    const onFocus = () => void loadFreshness(projectId);
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [projectId, loadSummary, loadFreshness]);

  // view catalog (availability depends on what the analyzers found in this project)
  useEffect(() => {
    if (!projectId) return;
    getJson<ViewInfo[]>(`/projects/${projectId}/views`)
      .then((catalog) => {
        setViews(catalog);
        setView((current) => {
          const cur = catalog.find((v) => v.id === current);
          return cur && cur.available ? current : (catalog.find((v) => v.available)?.id ?? "layers");
        });
      })
      .catch(() => setViews(FALLBACK_VIEWS));
  }, [projectId, reloadKey]);

  const viewForType = useCallback(
    (nodeType: string): string => {
      const hit = views.find((v) => v.available && v.best_for.includes(nodeType));
      return hit?.id ?? FALLBACK_BEST[nodeType] ?? "layers";
    },
    [views],
  );

  // ---- graph loading -------------------------------------------------------------------------
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    setGraphError(null);
    const params = new URLSearchParams();
    if (focusNodeId) params.set("focus_node_id", focusNodeId);
    if (view === "explore") {
      if (exploreExpanded.length) params.set("expanded", encodeExpandedIds(exploreExpanded));
      for (const [nid, off] of Object.entries(exploreChildOffsets)) {
        if (off > 0) params.append("extra_child_offsets", `${nid}=${off}`);
      }
    }
    const cacheKey =
      view === "explore"
        ? exploreCacheKey(exploreExpanded, exploreChildOffsets)
        : `${view}|${focusNodeId ?? ""}`;
    if (view === "explore") {
      const cached = exploreGraphCache.current.get(cacheKey);
      if (cached) {
        setPayload(cached);
        setGraphLoading(false);
        return;
      }
    }
    setGraphLoading(true);
    getJson<GraphPayload>(`/projects/${projectId}/graph/${view}?${params}`)
      .then((data) => {
        if (cancelled) return;
        setPayload(data);
        if (view === "explore") exploreGraphCache.current.set(cacheKey, data);
      })
      .catch((e) => {
        if (!cancelled) {
          setGraphError(e instanceof Error && e.message.includes("unknown view") ? e.message : "Could not load the graph. Is the API running on port 8000?");
          setPayload(null);
        }
      })
      .finally(() => {
        if (!cancelled) setGraphLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, view, focusNodeId, exploreExpanded, exploreChildOffsets, reloadKey]);

  useEffect(() => {
    if (view !== "explore" || !selectedId || !projectId) {
      setExploreNeighborIds(null);
      return;
    }
    let cancelled = false;
    const dir = "both";
    getJson<NeighborhoodPayload>(
      `/projects/${projectId}/graph/neighborhood?node_id=${encodeURIComponent(selectedId)}&direction=${dir}&depth=${focusDepth}`,
    )
      .then((nh) => {
        if (cancelled || nh.error) return;
        const raw = nh.reachable_ids ?? [...nh.neighbors_in, ...nh.neighbors_out];
        setExploreNeighborIds(new Set(raw.filter((id) => id !== selectedId)));
      })
      .catch(() => {
        if (!cancelled) setExploreNeighborIds(new Set());
      });
    return () => {
      cancelled = true;
    };
  }, [view, selectedId, projectId, focusDepth, payload?.view, payload?.nodes.length]);

  // ---- overlays (impact > path > tour/chat) --------------------------------------------------
  const special = useMemo(() => {
    if (impact) {
      const p = impactToPayload(impact);
      const hops = new Map(p.nodes.map((n) => [n.id, 0]));
      for (const c of impact.changed) hops.set(c.id, 0);
      for (const a of impact.affected) hops.set(a.id, a.hops ?? 1);
      return { kind: "impact" as const, payload: p, overlay: { ids: new Set(p.nodes.map((n) => n.id)), hops } };
    }
    if (pathResult?.found) {
      const p = pathToPayload(pathResult);
      return {
        kind: "path" as const,
        payload: p,
        overlay: { ids: new Set(p.nodes.map((n) => n.id)), order: pathResult.node_ids, edgeIds: new Set(p.edges.map((e) => e.id)) },
      };
    }
    return null;
  }, [impact, pathResult]);

  const overlay: Overlay | null = useMemo(() => {
    if (special) return special.overlay;
    const ids = tourIds.length ? tourIds : chatIds;
    if (!ids.length || !payload) return null;
    // only overlay when something highlighted is actually on this canvas
    const present = ids.filter((id) => payload.nodes.some((n) => n.id === id));
    return present.length ? { ids: new Set(present) } : null;
  }, [special, tourIds, chatIds, payload]);

  const displayed = special?.payload ?? payload;

  const detailForInspector = useMemo(() => {
    if (!detail || view !== "explore" || !payload) return detail;
    const gn = payload.nodes.find((n) => n.id === detail.node.id);
    if (!gn?.properties) return detail;
    return {
      ...detail,
      node: {
        ...detail.node,
        properties: { ...detail.node.properties, ...(gn.properties as Record<string, unknown>) },
      },
    };
  }, [detail, view, payload]);

  const exploreInspector = useMemo(() => {
    if (view !== "explore" || !selectedId || !payload) return undefined;
    const n = payload.nodes.find((x) => x.id === selectedId);
    const p = n?.properties as Record<string, unknown> | undefined;
    if (!p || !p.explore_expandable) return undefined;
    return {
      expandable: true,
      expanded: Boolean(p.explore_expanded),
      childCount: Number(p.child_count ?? 0),
    };
  }, [view, selectedId, payload]);

  const exploreInspectorEdge = useMemo(() => {
    if (view !== "explore" || !exploreEdgeDetail) return undefined;
    const src = payload?.nodes.find((n) => n.id === exploreEdgeDetail.edge.source);
    const tgt = payload?.nodes.find((n) => n.id === exploreEdgeDetail.edge.target);
    return {
      edge: exploreEdgeDetail.edge,
      payload: exploreEdgeDetail.underlying,
      loading: exploreEdgeDetail.loading,
      sourceLabel: src?.label ?? exploreEdgeDetail.edge.source,
      targetLabel: tgt?.label ?? exploreEdgeDetail.edge.target,
    };
  }, [view, exploreEdgeDetail, payload?.nodes]);

  const reducedMotion =
    typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---- layout --------------------------------------------------------------------------------
  const visibleLayers = useMemo(() => {
    const present = payload?.metadata?.layers;
    const counts = new Map((present ?? []).map((l) => [l.id, l.count]));
    return layers.filter((l) => counts.has(l.id)).map((l) => ({ ...l, count: counts.get(l.id) }));
  }, [layers, payload]);

  const exploreHighlight =
    view === "explore" && selectedId && exploreNeighborIds !== null ? exploreNeighborIds : undefined;

  const exploreHighlightRef = useRef(exploreHighlight);
  exploreHighlightRef.current = exploreHighlight;

  type ExploreCrumb = { id: string; label: string };
  const exploreBreadcrumbs = useMemo((): ExploreCrumb[] => {
    if (view !== "explore" || !selectedId || !payload) return [];
    const byId = new Map(payload.nodes.map((n) => [n.id, n]));
    const cur = byId.get(selectedId);
    if (!cur) return [];
    let p: string | null | undefined = (cur.properties?.parent_id as string | null | undefined) ?? null;
    const stack: ExploreCrumb[] = [{ id: cur.id, label: cur.label }];
    let g = 0;
    while (p && g++ < 64) {
      const n = byId.get(p);
      if (!n) break;
      stack.unshift({ id: n.id, label: n.label });
      p = (n.properties?.parent_id as string | null | undefined) ?? null;
    }
    const repo = activeProject?.name ?? "Repository";
    return [{ id: "__repo", label: repo }, ...stack];
  }, [view, selectedId, payload, activeProject?.name]);

  const orderedAncestorPath = useMemo(() => {
    if (!exploreBreadcrumbs.length) return [];
    return exploreBreadcrumbs.filter((c) => c.id !== "__repo").map((c) => c.id);
  }, [exploreBreadcrumbs]);

  useEffect(() => {
    exploreFitReason.current = "view";
  }, [view]);

  useEffect(() => {
    if (!graphLoading) setExploreLoadingId(null);
  }, [graphLoading]);

  const toggleExploreExpand = useCallback((id: string) => {
    setExploreLoadingId(id);
    exploreLastToggleId.current = id;
    exploreDispatch({ type: "toggle", id });
    exploreFitReason.current = null;
  }, []);

  const resetExploreTop = useCallback(() => {
    exploreDispatch({ type: "reset" });
    exploreGraphCache.current = new ExploreGraphCache(20);
    explorePrevPos.current = new Map();
    exploreFitReason.current = "reset";
  }, []);

  const exploreBack = useCallback(() => {
    exploreDispatch({ type: "back" });
    exploreFitReason.current = null;
  }, []);

  const expandExploreChildrenOfSelection = useCallback(() => {
    if (!selectedId) return;
    const p = payload?.nodes.find((x) => x.id === selectedId)?.properties as Record<string, unknown> | undefined;
    if (!p?.explore_expandable || p.explore_expanded) return;
    toggleExploreExpand(selectedId);
  }, [selectedId, payload?.nodes, toggleExploreExpand]);

  useEffect(() => {
    return () => {
      if (exploreClickTimer.current) clearTimeout(exploreClickTimer.current);
    };
  }, []);

  const loadMoreStructuralPage = useCallback((id: string) => {
    setExploreLoadingId(id);
    exploreDispatch({ type: "loadMoreChildren", nodeId: id });
    exploreFitReason.current = null;
  }, []);

  // Non-Explore views re-render on selection (cheap dagre/lane layout + highlight). Explore keeps
  // selection out of this effect so a click never triggers an ELK relayout.
  const nonExploreSelectedId = displayed && displayed.view !== "explore" ? selectedId : null;

  /** Structure + ELK: omit selection/neighbour highlight so clicking doesn't relayout. */
  useEffect(() => {
    if (!displayed) {
      setNodes([]);
      setEdges([]);
      exploreLaidOutFlowRef.current = null;
      return;
    }
    if (displayed.view !== "explore") {
      exploreLaidOutFlowRef.current = null;
      const flow = buildFlow(displayed, {
        layers,
        hiddenLayers,
        filter,
        selectedId: nonExploreSelectedId,
        overlay,
        exploreNeighborIds: null,
        selectedEdgeId,
        exploreLoadingId,
        onExploreToggle: toggleExploreExpand,
        onExploreLoadMore: loadMoreStructuralPage,
      });
      setEdges(flow.edges);
      setNodes(flow.nodes);
      return;
    }

    const flow = buildFlow(displayed, {
      layers,
      hiddenLayers,
      filter,
      selectedId: exploreSelectedIdRef.current,
      overlay,
      exploreNeighborIds: exploreHighlightRef.current ?? null,
      selectedEdgeId,
      exploreLoadingId,
      onExploreToggle: toggleExploreExpand,
      onExploreLoadMore: loadMoreStructuralPage,
    });
    setEdges(flow.edges);

    if (!flow.exploreLayoutInput) {
      setNodes(flow.nodes);
      exploreLaidOutFlowRef.current = null;
      return;
    }

    const layoutGen = ++exploreLayoutGenRef.current;
    let cancelled = false;
    const prevSeed = new Map<string, { x: number; y: number }>();
    for (const [id, p] of explorePrevPos.current) prevSeed.set(id, { x: p.x, y: p.y });
    const firstLayout = explorePrevPos.current.size === 0;
    void layoutExploreNodes(flow.exploreLayoutInput, prevSeed).then((pos) => {
      if (cancelled || layoutGen !== exploreLayoutGenRef.current) return;
      const next = new Map<string, { x: number; y: number }>();
      const dur = reducedMotion ? 0 : 180;
      const withPos = flow.nodes.map((n) => {
        const lp = pos.get(n.id);
        if (!lp) return n;
        next.set(n.id, { x: lp.x, y: lp.y });
        return { ...n, position: { x: lp.x, y: lp.y }, width: lp.width, height: lp.height };
      });
      explorePrevPos.current = next;
      const styledFlow = buildFlow(displayed, {
        layers,
        hiddenLayers,
        filter,
        selectedId: exploreSelectedIdRef.current,
        overlay,
        exploreNeighborIds: exploreHighlightRef.current ?? null,
        selectedEdgeId,
        exploreLoadingId,
        onExploreToggle: toggleExploreExpand,
        onExploreLoadMore: loadMoreStructuralPage,
      });
      const merged = mergeExploreLayoutPositions(withPos, styledFlow);
      exploreLaidOutFlowRef.current = { nodes: merged.nodes, edges: merged.edges, gen: layoutGen };

      flushSync(() => {
        setNodes(merged.nodes);
        setEdges(merged.edges);
      });

      const scheduleFit = () =>
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            if (layoutGen !== exploreLayoutGenRef.current) return;
            // While an expand/collapse is still fetching, this layout shows the *old* payload:
            // don't move the camera or consume the toggle marker yet.
            if (exploreLoadingId) return;
            const tid = exploreLastToggleId.current;
            const reason = exploreFitReason.current;
            const fitOpts = {
              padding: 0.18,
              duration: dur,
              minZoom: 0.35,
              maxZoom: 1.6 as number | undefined,
              nodes: merged.nodes,
              includeHiddenNodes: true,
            };
            if (reason === "view" || reason === "reset") {
              exploreFitReason.current = null;
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
              exploreLastToggleId.current = null;
            } else if (firstLayout) {
              void fitView(fitOpts);
            }
            // Otherwise (selection, edge click, loading indicator, overlay) keep the camera where the user left it.
          });
        });
      scheduleFit();
    });
    return () => {
      cancelled = true;
    };
  }, [
    nonExploreSelectedId,
    displayed,
    layers,
    hiddenLayers,
    filter,
    overlay,
    selectedEdgeId,
    exploreLoadingId,
    toggleExploreExpand,
    loadMoreStructuralPage,
    setNodes,
    setEdges,
    reducedMotion,
    fitView,
    fitBounds,
  ]);

  /** Explore only: update highlights when selection / neighbourhood changes — keep ELK positions. */
  useEffect(() => {
    if (view !== "explore" || !displayed || displayed.view !== "explore") return;
    const base = exploreLaidOutFlowRef.current;
    if (!base || base.gen !== exploreLayoutGenRef.current) return;
    const flow = buildFlow(displayed, {
      layers,
      hiddenLayers,
      filter,
      selectedId,
      overlay,
      exploreNeighborIds: exploreHighlight ?? null,
      selectedEdgeId,
      exploreLoadingId,
      onExploreToggle: toggleExploreExpand,
      onExploreLoadMore: loadMoreStructuralPage,
    });
    const merged = mergeExploreLayoutPositions(base.nodes, flow);
    exploreLaidOutFlowRef.current = { ...merged, gen: base.gen };
    setNodes(merged.nodes);
    setEdges(merged.edges);
  }, [
    view,
    displayed,
    layers,
    hiddenLayers,
    filter,
    selectedId,
    overlay,
    exploreHighlight,
    selectedEdgeId,
    exploreLoadingId,
    toggleExploreExpand,
    loadMoreStructuralPage,
    setNodes,
    setEdges,
  ]);

  const exploreLayoutSig = `${projectId}|${displayed?.view}|${focusNodeId}|${displayed?.nodes.length}|${hiddenLayers.size}|${filter}`;
  useEffect(() => {
    if (view === "explore") return;
    const dur = reducedMotion ? 0 : 300;
    const t = setTimeout(() => void fitView({ padding: 0.15, duration: dur }), 60);
    return () => clearTimeout(t);
  }, [exploreLayoutSig, fitView, reducedMotion, view]);

  // ---- source --------------------------------------------------------------------------------
  const loadSource = useCallback(
    async (path: string, start: number, end: number, hot: [number, number] | null) => {
      if (!projectId) return;
      try {
        const params = new URLSearchParams({ path, start: String(Math.max(1, start)), end: String(end) });
        setSource(await getJson<SourceSnippet>(`/projects/${projectId}/source?${params}`));
        setHighlight(hot);
      } catch {
        setSource(null);
        setHighlight(null);
      }
    },
    [projectId],
  );

  const openSource = useCallback(
    (path: string, line: number) => {
      setRightTab("inspector");
      void loadSource(path, line - 12, line + 60, [line, line]);
    },
    [loadSource],
  );

  // ---- selection -----------------------------------------------------------------------------
  const fetchExploreUnderlying = useCallback(
    async (edge: GraphEdge) => {
      if (!projectId || edge.edge_type === "CONTAINS") return;
      setSelectedEdgeId(edge.id);
      setExploreEdgeDetail({ edge, underlying: null, loading: true });
      setRightTab("inspector");
      setPanelOpen(true);
      const params = new URLSearchParams({ source: edge.source, target: edge.target });
      if (exploreExpanded.length) params.set("expanded", encodeExpandedIds(exploreExpanded));
      for (const [nid, off] of Object.entries(exploreChildOffsets)) {
        if (off > 0) params.append("extra_child_offsets", `${nid}=${off}`);
      }
      try {
        const data = await getJson<UnderlyingEdgesPayload>(`/projects/${projectId}/graph/edges?${params}`);
        setExploreEdgeDetail({ edge, underlying: data, loading: false });
      } catch {
        setExploreEdgeDetail({ edge, underlying: null, loading: false });
      }
    },
    [projectId, exploreExpanded, exploreChildOffsets],
  );

  useEffect(() => {
    if (view !== "explore") {
      setSelectedEdgeId(null);
      setExploreEdgeDetail(null);
    }
  }, [view]);

  const selectNode = useCallback(
    async (id: string) => {
      if (!projectId) return;
      setSelectedEdgeId(null);
      setExploreEdgeDetail(null);
      setSelectedId(id);
      setRightTab((t) => (t === "assistant" || t === "tour" || t === "endpoints" ? t : "inspector"));
      try {
        const d = await getJson<NodeDetail>(`/projects/${projectId}/nodes/${id}`);
        setDetail(d);
        const path = d.node.source_path;
        const start = d.node.start_line ?? 0;
        const isFile = d.node.node_type === "Module" || d.node.node_type === "Migration";
        if (path && (start || isFile)) {
          const first = start || 1;
          const last = isFile ? first + 120 : (d.node.end_line ?? first);
          await loadSource(path, first - 3, last + 3, isFile ? null : [first, d.node.end_line ?? first]);
        } else {
          setSource(null);
          setHighlight(null);
        }
      } catch {
        setDetail(null);
      }
    },
    [projectId, loadSource],
  );

  const onExploreBreadcrumbClick = useCallback(
    (crumbId: string) => {
      if (crumbId === "__repo") {
        resetExploreTop();
        exploreFitReason.current = "reset";
        return;
      }
      const idx = orderedAncestorPath.indexOf(crumbId);
      if (idx < 0) return;
      exploreDispatch({ type: "collapseToLevel", level: idx, orderedAncestors: orderedAncestorPath });
      exploreFitReason.current = null;
      void selectNode(crumbId);
    },
    [orderedAncestorPath, resetExploreTop, selectNode],
  );

  const expandAncestorsForNode = useCallback(
    async (nodeId: string) => {
      if (!projectId) return;
      const chain: string[] = [];
      let cur: string | null = nodeId;
      for (let guard = 0; guard < 64 && cur; guard += 1) {
        const nid: string = cur;
        const d = await getJson<NodeDetail>(`/projects/${projectId}/nodes/${nid}`);
        const parent: string | null =
          d.edges.find((edge) => edge.edge_type === "CONTAINS" && edge.target_id === nid)?.source_id ?? null;
        if (!parent) break;
        const pinfo = d.neighbors[parent];
        if (pinfo?.node_type === "Project") break;
        chain.unshift(parent);
        cur = parent;
      }
      exploreDispatch({ type: "expandPath", ancestors: chain });
      setView("explore");
    },
    [projectId],
  );

  /** Jump to any node: pick a fitting diagram if it's not on the current canvas, then select it. */
  const navigateTo = useCallback(
    async (id: string, nodeType?: string) => {
      setImpact(null);
      setPathResult(null);
      const onCanvas = payload?.nodes.some((n) => n.id === id);
      if (view === "explore" && !onCanvas) {
        await expandAncestorsForNode(id);
      } else if (!onCanvas && nodeType) {
        const target = viewForType(nodeType);
        const focusable = views.find((v) => v.id === target)?.focusable ?? false;
        setView(target);
        setFocusNodeId(focusable && nodeType !== "Model" ? id : undefined);
      }
      await selectNode(id);
    },
    [payload, selectNode, viewForType, views, view, expandAncestorsForNode],
  );

  const navigateById = useCallback(
    async (id: string) => {
      const type = detail?.neighbors[id]?.node_type;
      if (type) return navigateTo(id, type);
      try {
        const d = await getJson<NodeDetail>(`/projects/${projectId}/nodes/${id}`);
        navigateTo(id, d.node.node_type);
      } catch {
        void selectNode(id);
      }
    },
    [detail, navigateTo, projectId, selectNode],
  );

  // restore the selected node from a deep link once per project
  const restored = useRef(false);
  useEffect(() => {
    if (restored.current || !projectId || !payload) return;
    restored.current = true;
    const n = initialHash.current.n;
    if (n && projectId === initialHash.current.p) void selectNode(n);
  }, [projectId, payload, selectNode]);

  useEffect(() => {
    if (!projectId) return;
    const e =
      view === "explore" && exploreExpanded.length ? encodeExpandedIds(exploreExpanded) : undefined;
    writeHash({ p: projectId, v: view, f: focusNodeId, n: selectedId ?? undefined, e });
  }, [projectId, view, focusNodeId, selectedId, exploreExpanded]);

  // ⌘K / "/" palette · ⌘J ask · ⌘\ details pane · Esc clears overlays
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const typing = target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable;
      const mod = e.metaKey || e.ctrlKey;
      if ((mod && e.key.toLowerCase() === "k") || (e.key === "/" && !typing)) {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      } else if (mod && e.key.toLowerCase() === "j") {
        e.preventDefault();
        setPanelOpen(true);
        setRightTab("assistant");
      } else if (mod && e.key === "\\") {
        e.preventDefault();
        setPanelOpen((o) => !o);
      } else if (e.key === "Escape" && !typing) {
        setImpact(null);
        setPathResult(null);
        setChatIds([]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // ---- actions -------------------------------------------------------------------------------
  const resetSelection = () => {
    setSelectedId(null);
    setDetail(null);
    setSource(null);
    setHighlight(null);
    setImpact(null);
    setPathResult(null);
    setTourStep(null);
    setTourIds([]);
    setChatIds([]);
    setFocusNodeId(undefined);
    exploreDispatch({ type: "clearExplore" });
    exploreGraphCache.current = new ExploreGraphCache(20);
    explorePrevPos.current = new Map();
    setExploreNeighborIds(null);
    setSelectedEdgeId(null);
    setExploreEdgeDetail(null);
  };

  const onSearchPick = useCallback(
    (hit: SearchHit) => {
      void navigateTo(hit.id, hit.node_type);
    },
    [navigateTo],
  );

  const onTourSelect = (step: TourStep | null, index: number | null) => {
    setImpact(null);
    setPathResult(null);
    setTourStep(index);
    if (!step) {
      setTourIds([]);
      return;
    }
    setView(step.view);
    setFocusNodeId(step.view === "call-graph" ? step.node_ids[0] : undefined);
    setTourIds(step.node_ids);
  };

  const onTraceEndpoint = (ep: EndpointInfo) => {
    setImpact(null);
    setPathResult(null);
    setTourIds([]);
    setView("api-flow");
    setFocusNodeId(ep.id);
    void selectNode(ep.id);
  };

  const handleAnalyze = async (target: { git_url?: string; path?: string }) => {
    setIngestBusy(true);
    setIngestError(null);
    try {
      const body = await postJson<{ project: Project; summary: ProjectSummary }>("/projects/analyze", target);
      setProjects(await getJson<Project[]>("/projects"));
      resetSelection();
      setProjectId(body.project.id);
      setSummary(body.summary);
      setShowIngest(false);
      setReloadKey((k) => k + 1);
    } catch (e) {
      setIngestError(e instanceof Error ? e.message : "Analyze failed");
    } finally {
      setIngestBusy(false);
    }
  };

  const reindex = async () => {
    if (!projectId) return;
    setReindexing(true);
    try {
      let job = await postJson<Job>(`/projects/${projectId}/index?incremental=true`, {});
      while (job.status === "pending" || job.status === "running") {
        await new Promise((r) => setTimeout(r, 700));
        job = await getJson<Job>(`/projects/${projectId}/jobs/${job.id}`);
      }
      if (job.status === "failed") setGraphError(job.error ?? "Re-index failed");
      setImpact(null);
      setReloadKey((k) => k + 1);
      await Promise.all([loadSummary(projectId), loadFreshness(projectId)]);
      if (selectedId) void selectNode(selectedId);
    } finally {
      setReindexing(false);
    }
  };

  const showWorkingTreeImpact = () => {
    setRightTab("impact");
    setImpactToken((t) => t + 1);
  };

  const askAssistant = (question: string) => {
    setPanelOpen(true);
    setRightTab("assistant");
    setChatSeed({ text: question, token: Date.now() });
  };

  const toggleLayer = (id: string) =>
    setHiddenLayers((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const copyLink = () => {
    void navigator.clipboard?.writeText(window.location.href).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    });
  };

  const specialBanner = special
    ? special.kind === "impact"
      ? `Impact overlay · ${impact?.changed.filter((c) => c.node_type !== "Field").length ?? 0} changed, ${impact?.affected.length ?? 0} affected`
      : `Dependency path · ${(pathResult?.node_ids.length ?? 1) - 1} hop(s)`
    : null;

  const clearSpecial = () => {
    setImpact(null);
    setPathResult(null);
  };

  const groups = useMemo(() => {
    const order: string[] = [];
    const byGroup = new Map<string, ViewInfo[]>();
    for (const v of views) {
      if (!byGroup.has(v.group)) order.push(v.group);
      byGroup.set(v.group, [...(byGroup.get(v.group) ?? []), v]);
    }
    return order.map((g) => ({ group: g, items: byGroup.get(g)! }));
  }, [views]);

  const openTab = (tab: RightTab) => {
    setPanelOpen(true);
    setRightTab(tab);
  };

  const paletteActions: PaletteAction[] = [
    { id: "ask", label: "Ask a question", hint: "⌘J", icon: <MessageSquare size={16} strokeWidth={1.5} aria-hidden />, run: () => openTab("assistant") },
    { id: "routes", label: "Browse API routes", icon: <RouteIcon size={16} strokeWidth={1.5} aria-hidden />, run: () => openTab("endpoints") },
    { id: "tour", label: "Start the guided tour", icon: <BookOpen size={16} strokeWidth={1.5} aria-hidden />, run: () => openTab("tour") },
    {
      id: "impact",
      label: selectedId ? `Impact of changing ${detail?.node.name ?? "selection"}` : "Impact of uncommitted changes",
      icon: <GitFork size={16} strokeWidth={1.5} aria-hidden />,
      run: () => (selectedId ? openTab("impact") : showWorkingTreeImpact()),
    },
    { id: "reindex", label: "Re-index project", icon: <RefreshCw size={16} strokeWidth={1.5} aria-hidden />, run: () => void reindex() },
    { id: "copy", label: "Copy link to this view", icon: <LinkIcon size={16} strokeWidth={1.5} aria-hidden />, run: copyLink },
    { id: "panel", label: panelOpen ? "Hide details pane" : "Show details pane", hint: "⌘\\", run: () => setPanelOpen((o) => !o) },
    { id: "add", label: "Add a repository", icon: <Plus size={16} strokeWidth={1.5} aria-hidden />, run: () => setShowIngest(true) },
  ];

  const startResize = (e: React.PointerEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = panelWidth;
    const move = (ev: PointerEvent) => setPanelWidth(Math.min(640, Math.max(300, startW + (startX - ev.clientX))));
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      document.body.classList.remove("resizing");
    };
    document.body.classList.add("resizing");
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const visibleGroups = groups
    .map((g) => ({ ...g, items: g.items.filter((v) => v.available) }))
    .filter((g) => g.items.length > 0);

  // ---- render --------------------------------------------------------------------------------
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden />
          <span className="brand-title">Codebase Intelligence</span>
        </div>

        {projects.length > 0 ? (
          <label className="project-select">
            <span className="sr-only">Project</span>
            <select
              value={projectId}
              onChange={(e) => {
                resetSelection();
                setProjectId(e.target.value);
              }}
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {projectId && !showIngest ? (
          <button type="button" className="search-trigger" onClick={() => setPaletteOpen(true)}>
            <Search size={14} strokeWidth={1.5} aria-hidden />
            <span>Search code, views, actions…</span>
            <kbd>⌘K</kbd>
          </button>
        ) : (
          <span />
        )}

        <div className="topbar-controls">
          {projectId && !showIngest ? (
            <>
              <button type="button" className="icon-btn" onClick={copyLink} title="Copy link to this view" aria-label="Copy link to this view">
                {copied ? <Check size={16} strokeWidth={1.5} aria-hidden /> : <LinkIcon size={16} strokeWidth={1.5} aria-hidden />}
              </button>
              <a className="icon-btn" href={`${API}/projects/${projectId}/export`} download title="Export graph as JSON" aria-label="Export graph as JSON">
                <Download size={16} strokeWidth={1.5} aria-hidden />
              </a>
              <button type="button" className="icon-btn" onClick={() => setShowIngest(true)} title="Add a repository" aria-label="Add a repository">
                <Plus size={16} strokeWidth={1.5} aria-hidden />
              </button>
              <button type="button" className="btn primary" onClick={() => openTab("assistant")}>
                <MessageSquare size={14} strokeWidth={1.5} aria-hidden />
                Ask
                <kbd className="kbd-on-accent">⌘J</kbd>
              </button>
            </>
          ) : null}
        </div>
      </header>

      <FreshnessBanner freshness={freshness} busy={reindexing} onReindex={reindex} onShowImpact={showWorkingTreeImpact} />

      {showIngest ? (
        <main className="ingest-layout">
          <IngestPanel onAnalyze={handleAnalyze} busy={ingestBusy} error={ingestError} />
          {projects.length > 0 ? (
            <button type="button" className="btn ghost ingest-back" onClick={() => setShowIngest(false)}>
              Back to workspace
            </button>
          ) : null}
        </main>
      ) : (
        <div className={`dashboard ${panelOpen ? "" : "panel-closed"}`} style={{ ["--panel-w" as string]: `${panelWidth}px` }}>
          <aside className="sidebar" aria-label="Views">
            <nav className="view-nav">
              {visibleGroups.map(({ group, items }) => (
                <div key={group} className="view-group">
                  <p className="view-group-label">{group}</p>
                  {items.map((meta) => (
                    <button
                      key={meta.id}
                      type="button"
                      aria-current={view === meta.id && !special ? "page" : undefined}
                      className={`view-nav-item ${view === meta.id && !special ? "active" : ""}`}
                      onClick={() => {
                        clearSpecial();
                        setTourIds([]);
                        setTourStep(null);
                        viewChosenRef.current = true;
                        setView(meta.id);
                        setFocusNodeId(undefined);
                      }}
                    >
                      <ViewIcon id={meta.id} />
                      <span className="view-nav-title">{meta.label}</span>
                      {meta.count ? <span className="view-nav-count">{meta.count}</span> : null}
                    </button>
                  ))}
                </div>
              ))}
            </nav>

            <LayerLegend layers={visibleLayers} hidden={hiddenLayers} onToggle={toggleLayer} />

            {projects.length === 0 ? (
              <div className="empty-hint">
                <p>No repository yet.</p>
                <button type="button" className="btn secondary small" onClick={() => setShowIngest(true)}>
                  Add a repository
                </button>
              </div>
            ) : null}
          </aside>

          <section className={`canvas-area ${view === "explore" ? "canvas-area--explore" : ""}`} aria-label="Diagram">
            <ProjectSummaryCard
              projectName={activeProject?.name ?? "Project"}
              gitUrl={activeProject?.git_url}
              summary={summary}
              loading={summaryLoading}
              onPickNode={(id) => void navigateById(id)}
            />
            <div className={`canvas-toolbar ${view === "explore" && !special ? "canvas-toolbar--explore" : ""}`}>
              <div className="canvas-title">
                <ViewIcon id={view} />
                <h2>{currentView?.label ?? view}</h2>
                <span className="muted canvas-desc">{currentView?.description}</span>
              </div>
              {view === "explore" && !special && exploreBreadcrumbs.length > 0 ? (
                <nav className="explore-breadcrumbs" aria-label="Selection path">
                  {exploreBreadcrumbs.map((c, i) => (
                    <span key={c.id} className="explore-crumb-wrap">
                      {i > 0 ? <span className="explore-crumb-sep" aria-hidden /> : null}
                      <button
                        type="button"
                        className={`link-btn explore-crumb ${selectedId === c.id ? "active" : ""}`}
                        onClick={() => onExploreBreadcrumbClick(c.id)}
                      >
                        {c.label}
                      </button>
                    </span>
                  ))}
                </nav>
              ) : null}
              <label className="search-field">
                <Filter size={14} strokeWidth={1.5} aria-hidden className="search-icon" />
                <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter diagram" aria-label="Filter the diagram" />
              </label>
              {view === "explore" && !special ? (
                <div className="canvas-toolbar-explore" role="group" aria-label="Explore controls">
                  <span className="muted explore-hint">
                    {exploreExpanded.length ? `${exploreExpanded.length} expanded` : "Chevron expands · double-click zooms"}
                  </span>
                  <button
                    type="button"
                    className="icon-btn"
                    onClick={exploreBack}
                    disabled={!exploreState.history.length}
                    title="Back"
                    aria-label="Back one expand"
                  >
                    <ArrowLeft size={16} strokeWidth={1.5} aria-hidden />
                  </button>
                  <button type="button" className="icon-btn" onClick={resetExploreTop} title="Reset to top level" aria-label="Reset explore">
                    <ChevronsLeft size={16} strokeWidth={1.5} aria-hidden />
                  </button>
                  <label className="muted explore-depth">
                    Collapse to
                    <select
                      aria-label="Collapse explore to level"
                      onChange={(e) => {
                        const lv = Number(e.target.value);
                        e.target.value = "";
                        if (!lv) return;
                        exploreDispatch({
                          type: "collapseToLevel",
                          level: lv,
                          orderedAncestors: orderedAncestorPath,
                        });
                        exploreFitReason.current = null;
                      }}
                      defaultValue=""
                    >
                      <option value="" disabled>
                        level…
                      </option>
                      <option value={1}>1</option>
                      <option value={2}>2</option>
                      <option value={3}>3</option>
                    </select>
                  </label>
                  <button
                    type="button"
                    className="icon-btn"
                    onClick={expandExploreChildrenOfSelection}
                    disabled={!selectedId}
                    title="Expand children of selection"
                    aria-label="Expand children of selection"
                  >
                    <Plus size={16} strokeWidth={1.5} aria-hidden />
                  </button>
                  <label className="muted explore-depth">
                    Depth
                    <select
                      value={focusDepth}
                      onChange={(e) => setFocusDepth(Number(e.target.value))}
                      aria-label="Neighbourhood depth"
                    >
                      <option value={1}>1</option>
                      <option value={2}>2</option>
                      <option value={3}>3</option>
                    </select>
                  </label>
                </div>
              ) : null}
              {focusNodeId && !special ? (
                <button type="button" className="chip-btn" onClick={() => setFocusNodeId(undefined)}>
                  Focused <X size={12} strokeWidth={1.5} aria-hidden />
                </button>
              ) : null}
              {chatIds.length && !special ? (
                <button type="button" className="chip-btn" onClick={() => setChatIds([])}>
                  Highlighted {chatIds.length} <X size={12} strokeWidth={1.5} aria-hidden />
                </button>
              ) : null}
              <button type="button" className="icon-btn" onClick={() => setReloadKey((k) => k + 1)} title="Reload diagram" aria-label="Reload diagram">
                <RefreshCw size={16} strokeWidth={1.5} aria-hidden />
              </button>
              <button
                type="button"
                className="icon-btn"
                onClick={() => setPanelOpen((o) => !o)}
                title={`${panelOpen ? "Hide" : "Show"} details (⌘\\)`}
                aria-label={`${panelOpen ? "Hide" : "Show"} details pane`}
              >
                {panelOpen ? <PanelRightClose size={16} strokeWidth={1.5} aria-hidden /> : <PanelRightOpen size={16} strokeWidth={1.5} aria-hidden />}
              </button>
            </div>

            <div className="graph-pane">
              {graphLoading ? (
                <div className="graph-skeleton" aria-busy="true" aria-label="Loading diagram">
                  {[0, 1, 2, 3, 4].map((i) => (
                    <span key={i} className="skeleton skeleton-node" style={{ left: `${12 + (i % 3) * 28}%`, top: `${20 + Math.floor(i / 3) * 34 + (i % 2) * 8}%` }} />
                  ))}
                </div>
              ) : null}
              {graphError ? (
                <div className="graph-overlay error" role="alert">
                  <strong>Couldn't load this diagram.</strong>
                  <span>{graphError}</span>
                  <button type="button" className="btn secondary small" onClick={() => setReloadKey((k) => k + 1)}>
                    Try again
                  </button>
                </div>
              ) : null}
              {!graphLoading && !graphError && displayed && displayed.nodes.length === 0 ? (
                <div className="graph-overlay">
                  <strong>Nothing to show here yet.</strong>
                  <span className="muted">Try another view, or clear the filter.</span>
                </div>
              ) : null}
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={NODE_TYPES}
                nodesDraggable={view !== "explore"}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onlyRenderVisibleElements
                onNodeClick={(_, node) => {
                  if (node.type === "lane") return;
                  if (view === "explore" && !special) {
                    if (exploreClickTimer.current) clearTimeout(exploreClickTimer.current);
                    exploreClickTimer.current = setTimeout(() => {
                      setPanelOpen(true);
                      void selectNode(node.id);
                    }, 220);
                    return;
                  }
                  setPanelOpen(true);
                  void selectNode(node.id);
                }}
                onNodeDoubleClick={(_, node) => {
                  if (node.type === "lane") return;
                  if (special) return;
                  if (view === "explore") {
                    if (exploreClickTimer.current) {
                      clearTimeout(exploreClickTimer.current);
                      exploreClickTimer.current = null;
                    }
                    const kids = getNodes().filter((n) => n.parentId === node.id);
                    const dur = reducedMotion ? 0 : 200;
                    void fitView({
                      nodes: kids.length ? [node, ...kids] : [node],
                      padding: 0.3,
                      duration: dur,
                      includeHiddenNodes: true,
                    }).catch(() => undefined);
                    void selectNode(node.id);
                    return;
                  }
                  const data = node.data as ArchNodeData;
                  const type = data.nodeType;
                  if (currentView?.focusable) setFocusNodeId(node.id);
                  else void navigateTo(node.id, type);
                  if (currentView?.focusable) void selectNode(node.id);
                }}
                onEdgeClick={(_, edge) => {
                  setPanelOpen(true);
                  setRightTab("inspector");
                  if (view !== "explore" || special) return;
                  const ge = displayed?.edges.find((x) => x.id === edge.id);
                  if (ge) void fetchExploreUnderlying(ge);
                }}
                minZoom={view === "explore" ? 0.25 : 0.1}
                maxZoom={1.8}
                proOptions={{ hideAttribution: true }}
              >
                <MiniMap
                  pannable
                  zoomable
                  nodeColor={(n) => (n.data as ArchNodeData | undefined)?.color ?? "#CFCBC1"}
                  nodeStrokeWidth={0}
                  maskColor="rgba(247, 246, 242, 0.7)"
                  style={{ width: 150, height: 96 }}
                  bgColor="#FCFBF8"
                />
                <Controls showInteractive={false} />
                <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#DCD8CF" />
                {specialBanner ? (
                  <Panel position="top-left" className="graph-legend">
                    <span className="overlay-title">{specialBanner}</span>
                    <button type="button" className="link-btn" onClick={clearSpecial}>
                      Exit
                    </button>
                  </Panel>
                ) : null}
                {displayed?.metadata?.truncated ? (
                  <Panel position="top-right" className="graph-legend">
                    <span className="muted">
                      {displayed.metadata?.truncation_reason ??
                        "Showing the most connected nodes. Filter or search to narrow down."}
                    </span>
                  </Panel>
                ) : null}
              </ReactFlow>
            </div>
          </section>

          <aside className="right-panel" aria-label="Details" hidden={!panelOpen}>
            <div className="panel-resize" onPointerDown={startResize} role="separator" aria-orientation="vertical" aria-label="Resize details pane" />
            <div className="panel-tabs" role="tablist">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={rightTab === t.id}
                  className={`${rightTab === t.id ? "active" : ""} ${t.secondary ? "secondary" : ""}`}
                  onClick={() => setRightTab(t.id)}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <div className={`panel-body ${rightTab === "assistant" ? "assistant" : ""}`}>
              {rightTab === "inspector" ? (
                <Inspector
                  detail={detailForInspector}
                  source={source}
                  highlight={highlight}
                  layers={layers}
                  exploreEdge={exploreInspectorEdge}
                  explore={exploreInspector}
                  onToggleExplore={
                    exploreInspector && selectedId ? () => toggleExploreExpand(selectedId) : undefined
                  }
                  onNavigate={(id) => void navigateById(id)}
                  onFocus={(id) => {
                    clearSpecial();
                    const type = detail?.node.node_type;
                    const target = type ? viewForType(type) : view;
                    if (!views.find((v) => v.id === view)?.focusable) setView(target);
                    setFocusNodeId(id);
                  }}
                  onImpact={() => setRightTab("impact")}
                  onPathFrom={() => setRightTab("path")}
                  onAsk={askAssistant}
                />
              ) : null}
              {rightTab === "endpoints" ? (
                <EndpointsPanel
                  projectId={projectId}
                  reloadKey={reloadKey}
                  selectedId={selectedId}
                  onTrace={onTraceEndpoint}
                  onPickNode={(id) => void navigateById(id)}
                />
              ) : null}
              {rightTab === "tour" ? (
                <TourPanel
                  projectId={projectId}
                  layers={layers}
                  activeStep={tourStep}
                  onSelect={onTourSelect}
                  onPickNode={(id) => void navigateById(id)}
                />
              ) : null}
              {rightTab === "impact" ? (
                <ImpactPanel
                  projectId={projectId}
                  selectedNodeId={selectedId}
                  selectedNodeName={detail?.node.name}
                  report={impact}
                  onReport={(r) => {
                    setImpact(r);
                    setPathResult(null);
                  }}
                  onPickNode={(id) => void selectNode(id)}
                  autoRunToken={impactToken}
                />
              ) : null}
              {rightTab === "path" ? (
                <PathPanel
                  projectId={projectId}
                  selectedNodeId={selectedId}
                  selectedNodeName={detail?.node.name}
                  result={pathResult}
                  onResult={(r) => {
                    setPathResult(r);
                    setImpact(null);
                  }}
                  onPickNode={(id) => void selectNode(id)}
                />
              ) : null}
              {/* kept mounted so the conversation survives tab switches */}
              <div className="assistant-host" style={{ display: rightTab === "assistant" ? "flex" : "none" }}>
                <ChatPanel
                  projectId={projectId}
                  focusNodeId={selectedId}
                  focusNodeName={detail?.node.name}
                  onHighlightNodes={setChatIds}
                  onNavigateNode={(id) => void navigateById(id)}
                  onOpenSource={openSource}
                  seed={chatSeed}
                />
              </div>
            </div>
          </aside>
        </div>
      )}
      <CommandPalette
        open={paletteOpen}
        projectId={projectId}
        views={views}
        actions={paletteActions}
        onClose={() => setPaletteOpen(false)}
        onPickNode={(hit) => {
          setPanelOpen(true);
          onSearchPick(hit);
        }}
        onPickView={(id) => {
          clearSpecial();
          setTourIds([]);
          setView(id);
          setFocusNodeId(undefined);
        }}
      />
    </div>
  );
}

export default function App() {
  return (
    <ReactFlowProvider>
      <Dashboard />
    </ReactFlowProvider>
  );
}
