import type { Layer } from "./types";

export const VIEW_META: Record<string, { label: string; description: string; icon: string }> = {
  explore: {
    label: "Explore",
    description: "Drill down packages and modules without loading the whole graph",
    icon: "",
  },
  layers: {
    label: "Layers",
    description: "Modules, routes and models grouped by architectural layer",
    icon: "",
  },
  architecture: {
    label: "Architecture",
    description: "Apps and the weighted dependencies between them",
    icon: "",
  },
  "api-flow": {
    label: "API flow",
    description: "Route → handler → models/services, plus middleware",
    icon: "",
  },
  "call-graph": {
    label: "Call graph",
    description: "Callers and callees around a symbol",
    icon: "",
  },
  er: {
    label: "Data model",
    description: "ORM models with fields and relations",
    icon: "",
  },
  integrations: {
    label: "Integrations",
    description: "External services and who uses them",
    icon: "",
  },
  components: {
    label: "Components",
    description: "UI component tree and the API endpoints it calls",
    icon: "",
  },
};


/**
 * Presentation palette for layers (muted, paper-friendly). The API's layer colours were tuned for
 * the old dark theme; the UI maps layer ids to these and falls back to the API value.
 */
export const LAYER_COLORS: Record<string, string> = {
  api: "#55708F",
  middleware: "#6F7A45",
  service: "#3E7770",
  data: "#9C7A3C",
  ui: "#A15E45",
  config: "#8A867C",
  test: "#8A867C",
  external: "#7D6178",
};

export const DEFAULT_LAYERS: Layer[] = Object.entries(LAYER_COLORS).map(([id, color]) => ({
  id,
  name: id === "api" ? "API" : id === "ui" ? "UI" : id[0].toUpperCase() + id.slice(1),
  description: "",
  color,
}));

export const NEUTRAL = "#8A867C";
export const ACCENT = "#1F5C56";

export const EDGE_STYLE: Record<string, { color: string; dashed?: boolean; label: string }> = {
  ROUTES_TO: { color: "#55708F", label: "routes to" },
  HANDLES: { color: "#55708F", dashed: true, label: "handles" },
  CALLS: { color: "#9A958A", label: "calls" },
  IMPORTS: { color: "#B5B0A5", dashed: true, label: "imports" },
  READS_MODEL: { color: "#9C7A3C", label: "reads" },
  WRITES_MODEL: { color: "#A1412E", label: "writes" },
  FK_TO: { color: "#9C7A3C", dashed: true, label: "FK" },
  DEPENDS_ON: { color: "#7D6178", label: "depends" },
  SUBSCRIBES: { color: "#A15E45", label: "subscribes" },
  MIDDLEWARE: { color: "#6F7A45", label: "middleware" },
  CONTAINS: { color: "#CFCBC1", dashed: true, label: "contains" },
  QUERIES: { color: "#9C7A3C", label: "queries" },
  RENDERS: { color: "#A15E45", label: "renders" },
  HTTP_CALLS: { color: "#1F5C56", label: "HTTP" },
  INJECTS: { color: "#7D6178", dashed: true, label: "injects" },
};

/** Impact hops: changed → 1 → 2 → 3+, a single warm ramp rather than a rainbow. */
export const IMPACT_COLORS = ["#A1412E", "#B8673F", "#C99257", "#D8B98A"];

/** HTTP verbs share one muted family; meaning comes from the label, not the hue. */
export const METHOD_COLORS: Record<string, string> = {
  GET: "#3D7550",
  POST: "#55708F",
  PUT: "#94671E",
  PATCH: "#94671E",
  DELETE: "#A1412E",
  WS: "#7D6178",
};

export function layerColor(layers: Layer[], id?: string | null): string {
  if (id && LAYER_COLORS[id]) return LAYER_COLORS[id];
  return layers.find((l) => l.id === id)?.color ?? NEUTRAL;
}

export function layerName(layers: Layer[], id?: string | null): string | null {
  if (!id) return null;
  return layers.find((l) => l.id === id)?.name ?? id;
}
