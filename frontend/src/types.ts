export type Project = {
  id: string;
  name: string;
  root_path: string;
  framework?: string;
  commit_sha?: string;
  git_url?: string;
};

export type Layer = { id: string; name: string; description: string; color: string; count?: number };

export type GraphNode = {
  id: string;
  label: string;
  node_type: string;
  source_path?: string | null;
  layer?: string | null;
  complexity?: string | null;
  summary?: string | null;
  tags?: string[];
  confidence?: number;
  properties?: Record<string, unknown>;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  edge_type: string;
  confidence?: number;
  properties?: Record<string, unknown>;
};

export type GraphPayload = {
  view: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  metadata?: {
    layers?: Layer[];
    truncated?: boolean;
    truncation_reason?: string | null;
    node_count?: number;
    edge_count?: number;
    explore?: { expanded: string[]; project_id?: string };
  };
};

export type NeighborhoodPayload = {
  node_id: string;
  direction: string;
  depth: number;
  reachable_count: number;
  reachable_ids?: string[];
  edges: GraphEdge[];
  neighbors_in: string[];
  neighbors_out: string[];
  center: { id: string; name: string; node_type: string; source_path?: string | null; layer?: string | null };
  error?: string;
};

export type NeighborInfo = {
  id: string;
  name: string;
  node_type: string;
  source_path?: string | null;
  layer?: string | null;
};

export type NodeDetail = {
  node: {
    id: string;
    name: string;
    node_type: string;
    source_path?: string | null;
    start_line?: number | null;
    end_line?: number | null;
    qualified_name?: string | null;
    confidence?: number;
    properties: Record<string, unknown>;
  };
  edges: { id: string; edge_type: string; source_id: string; target_id: string; confidence?: number; properties?: Record<string, unknown> }[];
  neighbors: Record<string, NeighborInfo>;
};

export type SearchHit = {
  id: string;
  name: string;
  node_type: string;
  source_path?: string | null;
  start_line?: number | null;
  layer?: string | null;
  summary?: string | null;
  score: number;
};

export type TourStep = {
  order: number;
  title: string;
  description: string;
  lesson?: string | null;
  view: string;
  node_ids: string[];
  nodes: { id: string; name: string; node_type: string; source_path?: string | null; layer?: string | null }[];
};

export type ImpactItem = {
  id: string;
  name: string;
  node_type: string;
  source_path?: string | null;
  layer?: string | null;
  complexity?: string | null;
  hops?: number;
  via_name?: string;
};

export type ImpactReport = {
  source: "files" | "nodes" | "working-tree";
  changed_files: string[];
  changed: ImpactItem[];
  affected: ImpactItem[];
  affected_endpoints: ImpactItem[];
  edges: { id: string; source: string; target: string; edge_type: string }[];
  layers: { id: string; name: string; count: number }[];
  hotspots: (ImpactItem & { fan_in: number })[];
  risk: { level: "low" | "medium" | "high"; score: number };
  notes: string[];
  depth: number;
};

export type PathResult = {
  found: boolean;
  reason?: string;
  node_ids: string[];
  edges: { id: string; source: string; target: string; edge_type: string }[];
  nodes: NeighborInfo[];
};

export type Freshness = {
  status: "fresh" | "dirty" | "stale" | "unknown";
  message: string;
  changed_files: string[];
  changed_count?: number;
  indexed_at?: string;
};

export type Job = { id: string; status: "pending" | "running" | "completed" | "failed"; message: string; error?: string };

export type ViewInfo = {
  id: string;
  label: string;
  description: string;
  icon: string;
  group: string;
  focusable: boolean;
  best_for: string[];
  available: boolean;
  count: number | null;
};

export type NodeRef = {
  id: string;
  name: string;
  node_type: string;
  source_path?: string | null;
  line?: number | null;
};

export type EndpointInfo = NodeRef & {
  route: string;
  methods: string[];
  framework?: string | null;
  handler: NodeRef | null;
  guards: NodeRef[];
  dependencies: NodeRef[];
  callers: NodeRef[];
  models: (NodeRef & { access: string[] })[];
  external: NodeRef[];
  confidence: number;
};

export type Citation = {
  node_id: string;
  label: string;
  path?: string | null;
  line?: number | null;
  node_type?: string | null;
  view?: string | null;
  cited?: boolean;
};

export type ToolStep = { name: string; args: Record<string, unknown>; summary: string };

export type SourceSnippet = {
  path: string;
  start: number;
  end: number;
  total_lines: number;
  language?: string;
  abs_path?: string;
  content: string;
};

export type HttpCallInfo = { method?: string | null; url: string; line: number; endpoint_id?: string; endpoint?: string; external_host?: string };
