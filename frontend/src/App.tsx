import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Panel,
  PanOnScrollMode,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  useStore,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Activity,
  BookOpen,
  Check,
  Filter,
  FolderCog,
  Focus,
  GitFork,
  Lightbulb,
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
import { getJson, postJson } from "./api";
import { ApiKeyPrompt } from "./components/ApiKeyPrompt";
import { ApiEndpointList } from "./components/ApiEndpointList";
import { ArchNode, LaneLabel } from "./components/ArchNode";
import { RoutedEdge } from "./components/RoutedEdge";
import { EdgeLegend } from "./components/EdgeLegend";
import { ExportMenu } from "./components/ExportMenu";
import { ChatPanel } from "./components/ChatPanel";
import { CommandPalette, type PaletteAction } from "./components/CommandPalette";
import { EndpointsPanel } from "./components/EndpointsPanel";
import { FreshnessBanner } from "./components/FreshnessBanner";
import { ImpactPanel } from "./components/ImpactPanel";
import { IngestPanel } from "./components/IngestPanel";
import { Inspector } from "./components/Inspector";
import { LayerLegend } from "./components/LayerLegend";
import { PathPanel } from "./components/PathPanel";
import { SuggestionsPanel } from "./components/SuggestionsPanel";
import { ProjectSummaryCard, type ProjectSummary } from "./components/ProjectSummaryCard";
import { TourPanel } from "./components/TourPanel";
import { TraceControl } from "./components/TraceControl";
import { ProjectSwitcher } from "./components/ProjectSwitcher";
import { ProjectsPage } from "./components/ProjectsPage";
import { SavedViewsMenu } from "./components/SavedViewsMenu";
import { runIndexJob } from "./indexJobs";
import { ExploreToolbar } from "./explore/ExploreToolbar";
import { DEFAULT_TRACE, type TraceSettings } from "./trace";
import { type ArchNodeData, type Overlay } from "./flow";
import { ExploreGraphCache, exploreCacheKey } from "./explore/exploreGraphCache";
import { decodeExpandedIds, encodeExpandedIds } from "./explore/hash";
import { useExploreLayout, type ExploreFitReason } from "./explore/useExploreLayout";
import { createExploreState, exploreReducer } from "./explore/useExploreState";
import { DEFAULT_LAYERS, VIEW_META, zoomBucket } from "./graphTheme";
import { ViewIcon } from "./icons";
import type {
  EndpointInfo,
  Freshness,
  GraphPayload,
  UnderlyingEdgesPayload,
  ImpactReport,
  Job,
  Layer,
  GraphEdge,
  NodeDetail,
  PathResult,
  Project,
  ProjectOverview,
  SearchHit,
  SourceSnippet,
  TourStep,
  ViewInfo,
} from "./types";

const ZOOM_KEYS = ["Meta", "Control"];
const NODE_TYPES = { arch: ArchNode, lane: LaneLabel };
const EDGE_TYPES = { routed: RoutedEdge };

type RightTab = "inspector" | "endpoints" | "tour" | "impact" | "path" | "assistant" | "suggestions";
/** Primary tabs first; analysis tools are quieter and also reachable from ⌘K and node actions. */
const TABS: { id: RightTab; label: string; secondary?: boolean }[] = [
  { id: "inspector", label: "Details" },
  { id: "endpoints", label: "Routes" },
  { id: "assistant", label: "Ask" },
  { id: "tour", label: "Tour", secondary: true },
  { id: "impact", label: "Impact", secondary: true },
  { id: "path", label: "Path", secondary: true },
  { id: "suggestions", label: "Improve", secondary: true },
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
  const { fitView, getNodes } = useReactFlow();
  // Semantic zoom: re-render only when the zoom crosses a level, not on every wheel tick.
  const zoomLevel = useStore((st) => zoomBucket(st.transform[2]));
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
  const [exploreLoadingId, setExploreLoadingId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [exploreEdgeDetail, setExploreEdgeDetail] = useState<{
    edge: GraphEdge;
    underlying: UnderlyingEdgesPayload | null;
    loading: boolean;
  } | null>(null);
  const exploreGraphCache = useRef(new ExploreGraphCache(20));
  const exploreClickTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const exploreLastToggleId = useRef<string | null>(null);
  const exploreFitReason = useRef<ExploreFitReason>(null);
  const [trace, setTrace] = useState<TraceSettings>(DEFAULT_TRACE);
  const [levelBusy, setLevelBusy] = useState(false);
  const [levelNote, setLevelNote] = useState<string | null>(null);
  const [dimUnrelated, setDimUnrelated] = useState<boolean>(() => readPref("ci.dimUnrelated", true));
  useEffect(() => writePref("ci.dimUnrelated", dimUnrelated), [dimUnrelated]);
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
  const [ingestProgress, setIngestProgress] = useState<string | null>(null);
  const [showProjects, setShowProjects] = useState<false | "projects" | "activity" | "status">(false);
  const [overview, setOverview] = useState<ProjectOverview[] | null>(null);
  const refreshOverview = useCallback(() => {
    getJson<ProjectOverview[]>("/projects/overview")
      .then(setOverview)
      .catch(() => undefined);
  }, []);
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
  const traceCounts = useMemo(() => {
    let up = 0;
    let down = 0;
    for (const n of nodes) {
      const r = n.data?.traceRole;
      if (r === "up" || r === "both") up++;
      if (r === "down" || r === "both") down++;
    }
    return { up, down };
  }, [nodes]);
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
    refreshOverview();
  }, [refreshOverview]);

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
    // Poll while visible so a `git pull` (stale badge) or a re-index done elsewhere (git hook,
    // auto-refresh, CLI) shows up without a manual reload.
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void loadFreshness(projectId);
    }, 30_000);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.clearInterval(timer);
    };
  }, [projectId, loadSummary, loadFreshness]);

  // The index was rebuilt outside this tab (hook / auto-refresh / CLI): reload views and summary.
  const lastIndexedAt = useRef<{ id: string; at?: string } | null>(null);
  useEffect(() => {
    const at = freshness?.indexed_at;
    const prev = lastIndexedAt.current;
    lastIndexedAt.current = { id: projectId, at };
    if (prev && prev.id === projectId && prev.at && at && prev.at !== at) {
      exploreGraphCache.current = new ExploreGraphCache(20);
      setReloadKey((k) => k + 1);
      void loadSummary(projectId);
      refreshOverview();
    }
  }, [freshness?.indexed_at, projectId, loadSummary, refreshOverview]);

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
      // Full list (not the hash-capped encoding): a truncated list would silently drop expansions.
      if (exploreExpanded.length) params.set("expanded", exploreExpanded.join(","));
      for (const [nid, off] of Object.entries(exploreChildOffsets)) {
        if (off > 0) params.append("extra_child_offsets", `${nid}=${off}`);
      }
    }
    // reloadKey is bumped by re-index / reload, so cached payloads from before it are never reused.
    const cacheKey =
      view === "explore"
        ? `${projectId}|${reloadKey}|${exploreCacheKey(exploreExpanded, exploreChildOffsets)}`
        : `${view}|${focusNodeId ?? ""}`;
    if (view === "explore") {
      const cached = exploreGraphCache.current.get(cacheKey);
      if (cached) {
        setPayload(cached);
        setGraphLoading(false);
        // graphLoading may already be false, so the effect that clears this wouldn't re-run.
        setExploreLoadingId(null);
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

  const exploreMeta = payload?.view === "explore" ? payload.metadata?.explore : undefined;
  const selectedExpandable = useMemo(() => {
    if (view !== "explore" || !selectedId || !payload) return null;
    const n = payload.nodes.find((x) => x.id === selectedId);
    return n && n.properties?.explore_expandable ? n : null;
  }, [view, selectedId, payload]);

  /** Open the whole tree (or the selected package) down to `level`; the server applies the node budget. */
  const expandToLevel = useCallback(
    async (level: number) => {
      if (!projectId) return;
      setLevelBusy(true);
      setLevelNote(null);
      try {
        const params = new URLSearchParams({ expand_to_level: String(level) });
        if (exploreExpanded.length) params.set("expanded", exploreExpanded.join(","));
        if (selectedExpandable) params.set("level_root", selectedExpandable.id);
        const data = await getJson<GraphPayload>(`/projects/${projectId}/graph/explore?${params}`);
        const meta = data.metadata?.explore;
        const next = meta?.expanded ?? [];
        // Seed the cache so the reducer's new expanded set renders without a second request.
        exploreGraphCache.current.set(`${projectId}|${reloadKey}|${exploreCacheKey(next, {})}`, data);
        exploreFitReason.current = selectedExpandable ? null : "reset";
        if (selectedExpandable) exploreLastToggleId.current = selectedExpandable.id;
        exploreDispatch({ type: "set", expanded: next, childOffsets: {} });
        if (meta?.level_capped) {
          setLevelNote(
            `Opened to level ${meta.level_reached ?? "?"}: a full level ${(meta.level_reached ?? 1) + 1} is too big to draw, so only its busiest packages were opened. Select a package and use “Open in selection” to go deeper.`,
          );
        }
      } catch (e) {
        setLevelNote(e instanceof Error ? e.message : "Could not open levels");
      } finally {
        setLevelBusy(false);
      }
    },
    [projectId, exploreExpanded, selectedExpandable, reloadKey],
  );

  /** Keep only expansions above `level` (level 1 = just the top packages). */
  const collapseToLevel = useCallback(
    (level: number) => {
      const depths = exploreMeta?.expanded_depths ?? {};
      const keep = exploreExpanded.filter((id) => (depths[id] ?? 1) < level);
      exploreFitReason.current = "reset";
      setLevelNote(null);
      exploreDispatch({ type: "set", expanded: keep, childOffsets: {} });
    },
    [exploreExpanded, exploreMeta],
  );

  useExploreLayout({
    displayed,
    view,
    projectId,
    focusNodeId,
    layers,
    hiddenLayers,
    filter,
    overlay,
    selectedId,
    trace,
    selectedEdgeId,
    exploreLoadingId,
    dimUnrelated,
    onExploreToggle: toggleExploreExpand,
    onExploreLoadMore: loadMoreStructuralPage,
    setNodes,
    setEdges,
    reducedMotion,
    lastToggleId: exploreLastToggleId,
    fitReason: exploreFitReason,
  });

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
      if (exploreExpanded.length) params.set("expanded", exploreExpanded.join(","));
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

  /** Drop the node/edge selection (keeps the diagram, its expansions and any overlay). */
  const clearSelection = useCallback(() => {
    if (exploreClickTimer.current) clearTimeout(exploreClickTimer.current);
    setSelectedId(null);
    setDetail(null);
    setSource(null);
    setHighlight(null);
    setSelectedEdgeId(null);
    setExploreEdgeDetail(null);
  }, []);

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

  // A link pasted into an open tab (or back/forward) changes only the hash: apply it.
  // writeHash uses replaceState, which doesn't fire hashchange, so this only sees external edits.
  useEffect(() => {
    const onHash = () => {
      const h = readHash();
      if (h.p && h.p !== projectId && projects.some((p) => p.id === h.p)) setProjectId(h.p);
      if (h.v) {
        viewChosenRef.current = true;
        setView(h.v);
      }
      setFocusNodeId(h.f);
      exploreDispatch({ type: "set", expanded: h.e ? decodeExpandedIds(h.e) : [] });
      if (h.n) void selectNode(h.n);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [projectId, projects, selectNode]);

  const overlayActive = useRef(false);
  overlayActive.current = Boolean(impact || pathResult || chatIds.length);

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
        // First Esc leaves an overlay (impact / path / chat highlight); the next clears the selection.
        if (overlayActive.current) {
          setImpact(null);
          setPathResult(null);
          setChatIds([]);
        } else {
          clearSelection();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [clearSelection]);

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

  const pickFlowEndpoint = useCallback(
    (ep: EndpointInfo) => {
      setImpact(null);
      setPathResult(null);
      setTourIds([]);
      setFocusNodeId(ep.id);
      void selectNode(ep.id);
    },
    [selectNode],
  );

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
    setIngestProgress(target.git_url ? "Cloning repository…" : "Registering project…");
    try {
      // Register (clone) first, then index as a background job so progress can be shown.
      const project = await postJson<Project>("/projects", target);
      const job: Job = await runIndexJob(project.id, {
        incremental: false,
        onProgress: (j) => setIngestProgress(`${Math.round((j.progress ?? 0) * 100)}% · ${j.message || "Indexing…"}`),
      });
      if (job.status === "failed") throw new Error(job.error ?? "Indexing failed");
      setProjects(await getJson<Project[]>("/projects"));
      refreshOverview();
      resetSelection();
      setProjectId(project.id);
      setShowIngest(false);
      setShowProjects(false);
      setReloadKey((k) => k + 1);
    } catch (e) {
      setIngestError(e instanceof Error ? e.message : "Analyze failed");
    } finally {
      setIngestBusy(false);
      setIngestProgress(null);
    }
  };

  /** A project was removed (projects page): drop every cache that could still show it. */
  const onProjectRemoved = (id: string) => {
    exploreGraphCache.current = new ExploreGraphCache(20);
    refreshOverview();
    const rest = projects.filter((p) => p.id !== id);
    setProjects(rest);
    if (id === projectId) {
      resetSelection();
      setPayload(null);
      setSummary(null);
      setFreshness(null);
      setNodes([]);
      setEdges([]);
      const next = rest[0];
      setProjectId(next?.id ?? "");
      writeHash(next ? { p: next.id, v: view } : {});
      if (!next) {
        setShowProjects(false);
        setShowIngest(true);
      }
    }
  };

  const reindex = async (incremental = true) => {
    if (!projectId) return;
    setReindexing(true);
    try {
      const job = await runIndexJob(projectId, { incremental });
      exploreGraphCache.current = new ExploreGraphCache(20);
      refreshOverview();
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
    { id: "suggestions", label: "Show refactoring suggestions", icon: <Lightbulb size={16} strokeWidth={1.5} aria-hidden />, run: () => openTab("suggestions") },
    { id: "reindex", label: "Re-index changed files", icon: <RefreshCw size={16} strokeWidth={1.5} aria-hidden />, run: () => void reindex(true) },
    { id: "copy", label: "Copy link to this view", icon: <LinkIcon size={16} strokeWidth={1.5} aria-hidden />, run: copyLink },
    { id: "panel", label: panelOpen ? "Hide details pane" : "Show details pane", hint: "⌘\\", run: () => setPanelOpen((o) => !o) },
    { id: "add", label: "Add a repository", icon: <Plus size={16} strokeWidth={1.5} aria-hidden />, run: () => setShowIngest(true) },
    { id: "projects", label: "Manage projects (rename, settings, remove)", icon: <FolderCog size={16} strokeWidth={1.5} aria-hidden />, run: () => setShowProjects("projects") },
    { id: "activity", label: "Activity log", icon: <Activity size={16} strokeWidth={1.5} aria-hidden />, run: () => setShowProjects("activity") },
    { id: "status", label: "Server status", run: () => setShowProjects("status") },
    { id: "full-reindex", label: "Full re-index (rebuild from scratch)", run: () => void reindex(false) },
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
          <ProjectSwitcher
            projects={projects}
            overview={overview}
            projectId={projectId}
            onOpen={refreshOverview}
            onPick={(id) => {
              resetSelection();
              setShowProjects(false);
              setShowIngest(false);
              setProjectId(id);
            }}
            onManage={() => setShowProjects("projects")}
            onAdd={() => setShowIngest(true)}
          />
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
              <SavedViewsMenu
                projectId={projectId}
                describe={`${currentView?.label ?? view}${detail?.node.name ? ` · ${detail.node.name}` : ""}`}
                current={() => ({
                  v: view,
                  n: selectedId ?? undefined,
                  f: focusNodeId,
                  e: view === "explore" && exploreExpanded.length ? encodeExpandedIds(exploreExpanded) : undefined,
                })}
              />
              <button type="button" className="icon-btn" onClick={copyLink} title="Copy link to this view" aria-label="Copy link to this view">
                {copied ? <Check size={16} strokeWidth={1.5} aria-hidden /> : <LinkIcon size={16} strokeWidth={1.5} aria-hidden />}
              </button>
<ExportMenu
                projectId={projectId}
                projectName={activeProject?.name ?? "project"}
                viewLabel={currentView?.label ?? view}
                payload={displayed}
                nodes={nodes}
                edges={edges}
              />
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

      {showProjects && !showIngest ? null : (
        <FreshnessBanner freshness={freshness} busy={reindexing} onReindex={() => void reindex(true)} onShowImpact={showWorkingTreeImpact} />
      )}

      {showProjects && !showIngest ? (
        <ProjectsPage
          currentId={projectId}
          initialTab={showProjects}
          onOpen={(id) => {
            if (id !== projectId) {
              resetSelection();
              setProjectId(id);
            }
            setShowProjects(false);
          }}
          onAdd={() => setShowIngest(true)}
          onRemoved={onProjectRemoved}
          onRenamed={() => {
            void getJson<Project[]>("/projects").then(setProjects);
            refreshOverview();
          }}
          onIndexed={(id) => {
            refreshOverview();
            if (id === projectId) {
              exploreGraphCache.current = new ExploreGraphCache(20);
              setReloadKey((k) => k + 1);
              void loadSummary(id);
              void loadFreshness(id);
            }
          }}
          onClose={() => setShowProjects(false)}
        />
      ) : showIngest ? (
        <main className="ingest-layout">
          <IngestPanel onAnalyze={handleAnalyze} busy={ingestBusy} error={ingestError} progress={ingestProgress} />
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
            {displayed && displayed.nodes.length > 0 ? <EdgeLegend /> : null}

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
              <label className="search-field">
                <Filter size={14} strokeWidth={1.5} aria-hidden className="search-icon" />
                <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter diagram" aria-label="Filter the diagram" />
              </label>
              {view === "explore" && !special ? (
                <ExploreToolbar
                  expandedCount={exploreExpanded.length}
                  canGoBack={exploreState.history.length > 0}
                  maxDepth={exploreMeta?.max_depth}
                  scopeName={selectedExpandable?.label ?? null}
                  canExpandSelection={Boolean(selectedExpandable && !selectedExpandable.properties?.explore_expanded)}
                  busy={levelBusy}
                  onBack={exploreBack}
                  onReset={resetExploreTop}
                  onExpandToLevel={(lv) => void expandToLevel(lv)}
                  onCollapseToLevel={collapseToLevel}
                  onExpandSelection={expandExploreChildrenOfSelection}
                />
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
              <button
                type="button"
                className="icon-btn toggle-btn"
                aria-pressed={dimUnrelated}
                onClick={() => setDimUnrelated((d) => !d)}
                title={dimUnrelated ? "Focus mode on: unrelated nodes fade when you select" : "Focus mode off: selection only highlights"}
                aria-label="Fade nodes unrelated to the selection"
              >
                <Focus size={16} strokeWidth={1.5} aria-hidden />
              </button>
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

            <div className="graph-row">
            {view === "api-flow" && !special && projectId ? (
              <ApiEndpointList projectId={projectId} reloadKey={reloadKey} focusedId={focusNodeId} onPick={pickFlowEndpoint} />
            ) : null}
            <div
              className={`graph-pane zoom-${zoomLevel}`}
              onKeyDown={(e) => {
                // Enter on a focused node opens it (React Flow focuses node wrappers with Tab).
                if (e.key !== "Enter") return;
                const el = (e.target as HTMLElement).closest?.(".react-flow__node");
                const id = el?.getAttribute("data-id");
                if (!id || id.startsWith("__lane:") || e.target !== el) return;
                e.preventDefault();
                setPanelOpen(true);
                void selectNode(id);
              }}
            >
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
                edgeTypes={EDGE_TYPES}
                nodesDraggable={view !== "explore"}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onlyRenderVisibleElements
                // Trackpad-friendly: two-finger scroll pans, pinch zooms, ⌘/Ctrl + wheel zooms (mouse users).
                panOnScroll
                panOnScrollMode={PanOnScrollMode.Free}
                zoomOnScroll={false}
                zoomOnPinch
                zoomActivationKeyCode={ZOOM_KEYS}
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
                onPaneClick={clearSelection}
                // Edges get explicit z-indexes from buildFlow: context edges under every node,
                // the traced ones above the group boxes that contain their endpoints.
                zIndexMode="manual"
                minZoom={0.05}
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
              {view === "explore" && !special && exploreBreadcrumbs.length > 0 ? (
                <Panel position="top-left">
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
                </Panel>
              ) : null}
                {specialBanner ? (
                  <Panel position="top-left" className="graph-legend">
                    <span className="overlay-title">{specialBanner}</span>
                    <button type="button" className="link-btn" onClick={clearSpecial}>
                      Exit
                    </button>
                  </Panel>
                ) : null}
                {selectedId && !special && nodes.some((n) => n.id === selectedId) ? (
                  <Panel position="top-right">
                    <TraceControl
                      value={trace}
                      onChange={setTrace}
                      selectedName={detail?.node.name}
                      counts={traceCounts}
                      onClear={clearSelection}
                    />
                  </Panel>
                ) : null}
                {levelNote && view === "explore" ? (
                  <Panel position="bottom-center" className="graph-legend graph-note" role="status">
                    <span className="muted">{levelNote}</span>
                    <button type="button" className="link-btn" onClick={() => setLevelNote(null)}>
                      Dismiss
                    </button>
                  </Panel>
                ) : null}
                {displayed?.metadata?.truncated ? (
                  <Panel position="bottom-center" className="graph-legend">
                    <span className="muted">
                      {displayed.metadata?.truncation_reason ??
                        "Showing the most connected nodes. Filter or search to narrow down."}
                    </span>
                  </Panel>
                ) : null}
              </ReactFlow>
            </div>
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
                  title={t.id === "suggestions" ? "Refactoring and reuse suggestions" : undefined}
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
              {rightTab === "suggestions" ? (
                <SuggestionsPanel projectId={projectId} reloadKey={reloadKey} onPickNode={(id) => void navigateById(id)} />
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
      <ApiKeyPrompt />
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
