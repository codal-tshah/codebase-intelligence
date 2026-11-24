import { ChevronDown, ChevronRight, Copy, Crosshair, ExternalLink, GitFork, MessageSquare, Route } from "lucide-react";
import { useMemo, useState } from "react";
import { EDGE_STYLE, layerColor } from "../graphTheme";
import { highlightLines, languageOf } from "../highlight";
import { NodeIcon } from "../icons";
import { evidenceSummary, tierLabel } from "../evidence";
import type {
  EvidenceInfo,
  GraphEdge,
  HttpCallInfo,
  Layer,
  NodeDetail,
  SourceSnippet,
  UnderlyingEdgesPayload,
} from "../types";

type Props = {
  detail: NodeDetail | null;
  source: SourceSnippet | null;
  highlight: [number, number] | null;
  layers: Layer[];
  onNavigate: (id: string) => void;
  onFocus: (id: string) => void;
  onImpact: () => void;
  onPathFrom: () => void;
  onAsk: (question: string) => void;
  explore?: { expandable: boolean; expanded: boolean; childCount: number };
  onToggleExplore?: () => void;
  /** Explore aggregated edge selection (underlying edges from API). */
  exploreEdge?: {
    edge: GraphEdge;
    payload: UnderlyingEdgesPayload | null;
    loading: boolean;
    sourceLabel: string;
    targetLabel: string;
  };
};

export function Inspector({
  detail,
  source,
  highlight,
  layers,
  onNavigate,
  onFocus,
  onImpact,
  onPathFrom,
  onAsk,
  explore,
  onToggleExplore,
  exploreEdge,
}: Props) {
  if (!detail && !source && !exploreEdge) {
    return (
      <div className="placeholder">
        <p className="placeholder-title">Nothing selected</p>
        <p className="muted">Select a node in the diagram to see what it does, what it connects to, and its source.</p>
        <p className="muted">
          <kbd>⌘K</kbd> to search · In Explore, use the chevron on a node to expand, or double-click to zoom to it
        </p>
      </div>
    );
  }
  return (
    <>
      {exploreEdge ? <ExploreEdgeCard onNavigate={onNavigate} {...exploreEdge} /> : null}
      {detail ? (
        <NodeCard
          detail={detail}
          layers={layers}
          onNavigate={onNavigate}
          onFocus={onFocus}
          onImpact={onImpact}
          onPathFrom={onPathFrom}
          onAsk={onAsk}
          explore={explore}
          onToggleExplore={onToggleExplore}
          hasSource={Boolean(source)}
        />
      ) : null}
      {source || !detail ? <SourceView source={source} highlight={highlight} /> : null}
    </>
  );
}

function ExploreEdgeCard({
  edge,
  payload,
  loading,
  sourceLabel,
  targetLabel,
  onNavigate,
}: {
  edge: GraphEdge;
  payload: UnderlyingEdgesPayload | null;
  loading: boolean;
  sourceLabel: string;
  targetLabel: string;
  onNavigate: (id: string) => void;
}) {
  const props = edge.properties ?? {};
  const weight = Number(props.weight ?? 0);
  const byType = (props.by_type as Record<string, number> | undefined) ?? {};

  return (
    <div className="detail-card explore-edge-card">
      <div className="detail-header">
        <span className="badge">{edge.edge_type}</span>
        {loading ? (
          <span className="muted" aria-busy>
            Loading…
          </span>
        ) : null}
      </div>
      <h2 className="explore-edge-title">
        <button type="button" className="link-inline" title={edge.source} onClick={() => onNavigate(edge.source)}>
          {sourceLabel}
        </button>
        <span className="muted"> → </span>
        <button type="button" className="link-inline" title={edge.target} onClick={() => onNavigate(edge.target)}>
          {targetLabel}
        </button>
      </h2>
      <p className="muted">
        Confidence {Math.round((edge.confidence ?? 1) * 100)}%{weight > 1 ? ` · weight ${weight}` : ""}
        {props.aggregated ? " · aggregated" : ""}
      </p>
      {edge.evidence ? (
        <p className="evidence-line muted" title={edge.evidence.reason_code}>
          {evidenceSummary(edge.evidence)}
        </p>
      ) : null}
      {Object.keys(byType).length > 0 ? (
        <div className="chip-row">
          {Object.entries(byType).map(([t, c]) => (
            <span key={t} className="chip static">
              {EDGE_STYLE[t]?.label ?? t} ×{c}
            </span>
          ))}
        </div>
      ) : null}
      <details open>
        <summary>
          Underlying edges {payload ? <span className="muted">{payload.edges.length}</span> : null}
          {payload?.capped ? <span className="muted"> (capped)</span> : null}
        </summary>
        {payload && payload.edges.length > 0 ? (
          <ul className="explore-edge-list">
            {payload.edges.map((ue) => (
              <li key={ue.id}>
                <span className="mono">{ue.edge_type}</span>
                <button type="button" className="link-inline" onClick={() => onNavigate(ue.source_id)}>
                  {ue.source_id.slice(0, 10)}…
                </button>
                <span className="muted"> → </span>
                <button type="button" className="link-inline" onClick={() => onNavigate(ue.target_id)}>
                  {ue.target_id.slice(0, 10)}…
                </button>
                {ue.evidence ? (
                  <span className="muted evidence-inline" title={ue.evidence.reason_code}>
                    {" "}
                    · {tierLabel(ue.evidence.tier)}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        ) : !loading ? (
          <p className="muted">No underlying edges returned.</p>
        ) : null}
      </details>
    </div>
  );
}

function NodeCard({
  detail,
  layers,
  onNavigate,
  onFocus,
  onImpact,
  onPathFrom,
  onAsk,
  explore,
  onToggleExplore,
  hasSource,
}: Omit<Props, "source" | "highlight" | "detail"> & { detail: NodeDetail; hasSource: boolean }) {
  const { node, edges, neighbors } = detail;
  const props = node.properties ?? {};
  const layerId = props.layer as string | undefined;
  const layer = layers.find((l) => l.id === layerId);
  const tags = (props.tags as string[] | undefined) ?? [];
  const summary = props.summary as string | undefined;
  const httpCalls = (props.http_calls as HttpCallInfo[] | undefined) ?? [];
  const route = (props.route as string | undefined) ?? undefined;
  const confidence = node.confidence ?? 1;
  const isContainer = node.node_type === "Package" || node.node_type === "Project";

  const grouped = new Map<
    string,
    { id: string; dir: "out" | "in"; low: boolean; evidence?: EvidenceInfo; extractor?: string }[]
  >();
  for (const e of edges) {
    const out = e.source_id === node.id;
    // Containment: list what this node contains (its parent is already in the breadcrumbs).
    if (e.edge_type === "CONTAINS" && !out) continue;
    const key =
      e.edge_type === "CONTAINS" ? "Contains" : `${out ? "→" : "←"} ${EDGE_STYLE[e.edge_type]?.label ?? e.edge_type}`;
    const id = out ? e.target_id : e.source_id;
    const list = grouped.get(key) ?? [];
    if (!list.some((x) => x.id === id))
      list.push({
        id,
        dir: out ? "out" : "in",
        low: (e.confidence ?? 1) < 0.7,
        evidence: e.evidence,
        extractor: e.extractor,
      });
    grouped.set(key, list);
  }
  const unresolvedHttp = httpCalls.filter(
    (c) => c.match_variant === "unresolved" || (!c.endpoint_id && !c.external_host),
  );
  const linkedHttp = httpCalls.filter((c) => !unresolvedHttp.includes(c));

  const askAbout =
    node.node_type === "Endpoint"
      ? `What happens when ${(props.methods as string[] | undefined)?.join("/") ?? ""} ${route ?? node.name} is called? Trace it from the UI to the database.`
      : node.node_type === "Model"
        ? `Explain the ${node.name} model: its fields, relations, and which endpoints read or write it.`
        : node.node_type === "Component"
          ? `Explain the ${node.name} component: what it renders, where its data comes from, and which APIs it calls.`
          : `Explain ${node.name}: what it does, who calls it, and what would break if it changed.`;

  return (
    <>
      <div className="detail-card">
        <div className="detail-header">
          <span className="badge">
            <NodeIcon type={node.node_type} size={12} />
            {node.node_type}
          </span>
          {layer ? (
            <span className="badge badge-layer" style={{ ["--layer" as string]: layerColor(layers, layer.id) }}>
              {layer.name}
            </span>
          ) : null}
          {props.complexity ? (
            <span className={`pill pill--${props.complexity as string}`}>{props.complexity as string}</span>
          ) : null}
          {props.framework ? <span className="badge">{props.framework as string}</span> : null}
          {confidence < 0.8 ? (
            <span className="badge badge-warn" title="Inferred by heuristics; verify in source">
              confidence {Math.round(confidence * 100)}%
            </span>
          ) : null}
        </div>
        <h2>{node.name}</h2>
        {node.evidence ? (
          <p className="evidence-line muted" title={node.evidence.reason_code}>
            {evidenceSummary(node.evidence)}
          </p>
        ) : null}
        {summary ? <p className="detail-summary">{summary}</p> : null}
        {node.qualified_name && !sameAsPath(node.qualified_name, node.source_path) ? (
          <p className="mono muted">{node.qualified_name}</p>
        ) : null}
        {/* the source block below already shows the path */}
        {node.source_path && !hasSource ? (
          <p className="file-path">
            {node.source_path}
            {node.start_line ? `:${node.start_line}` : ""}
          </p>
        ) : null}
        {Array.isArray(props.methods) && props.methods.length > 0 ? (
          <div className="chip-row">
            {(props.methods as string[]).map((m) => (
              <span key={m} className={`method method--${m}`}>
                {m}
              </span>
            ))}
            {route ? <span className="mono">{route}</span> : null}
          </div>
        ) : route ? (
          <p className="mono muted">route {route}</p>
        ) : null}
        {tags.length > 0 ? (
          <div className="chip-row">
            {tags.map((t) => (
              <span key={t} className="chip static tag">
                #{t}
              </span>
            ))}
          </div>
        ) : null}
        <div className="detail-actions">
          {explore?.expandable && onToggleExplore ? (
            <button
              type="button"
              className="btn secondary small"
              onClick={onToggleExplore}
              title="Show or hide children under this node"
            >
              {explore.expanded ? (
                <>
                  <ChevronDown size={14} strokeWidth={1.5} aria-hidden />
                  Collapse
                </>
              ) : (
                <>
                  <ChevronRight size={14} strokeWidth={1.5} aria-hidden />
                  Expand{explore.childCount > 0 ? ` (${explore.childCount})` : ""}
                </>
              )}
            </button>
          ) : null}
          <button type="button" className="btn primary small" onClick={() => onAsk(askAbout)}>
            <MessageSquare size={14} strokeWidth={1.5} aria-hidden />
            Ask about this
          </button>
          <button
            type="button"
            className="btn ghost small"
            onClick={() => onFocus(node.id)}
            title="Show only this node's neighbourhood"
          >
            <Crosshair size={14} strokeWidth={1.5} aria-hidden />
            Focus
          </button>
          <button type="button" className="btn ghost small" onClick={onImpact} title="What would a change here affect?">
            <GitFork size={14} strokeWidth={1.5} aria-hidden />
            Impact
          </button>
          <button
            type="button"
            className="btn ghost small"
            onClick={onPathFrom}
            title="Trace a dependency path from here"
          >
            <Route size={14} strokeWidth={1.5} aria-hidden />
            Path
          </button>
        </div>
      </div>

      {linkedHttp.length > 0 ? (
        <div className="relations">
          <details open>
            <summary>
              HTTP requests <span className="muted">{linkedHttp.length}</span>
            </summary>
            <ul>
              {linkedHttp.map((c, i) => (
                <li key={i}>
                  <button
                    type="button"
                    disabled={!c.endpoint_id}
                    onClick={() => c.endpoint_id && onNavigate(c.endpoint_id)}
                  >
                    <span className={`method method--${c.method ?? "GET"}`}>{c.method ?? "GET"}</span>
                    <span className="impact-name mono">{c.url}</span>
                    <span className="impact-sub">
                      {c.endpoint ? `→ ${c.endpoint}` : c.external_host ? "external" : "unmatched"}
                    </span>
                    {c.evidence ? <span className="impact-sub muted">{tierLabel(c.evidence.tier)}</span> : null}
                  </button>
                </li>
              ))}
            </ul>
          </details>
        </div>
      ) : null}
      {unresolvedHttp.length > 0 ? (
        <div className="relations">
          <details open>
            <summary>
              Unresolved HTTP <span className="muted">{unresolvedHttp.length}</span>
            </summary>
            <ul>
              {unresolvedHttp.map((c, i) => (
                <li key={i}>
                  <span className={`method method--${c.method ?? "GET"}`}>{c.method ?? "GET"}</span>
                  <span className="impact-name mono">{c.url}</span>
                  <span className="impact-sub muted">
                    {c.evidence?.reason ?? "Backend endpoint could not be resolved"}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        </div>
      ) : null}

      {grouped.size > 0 ? (
        <div className="relations">
          {[...grouped.entries()]
            .sort(([a], [b]) => (a === "Contains" ? -1 : b === "Contains" ? 1 : 0))
            .map(([label, items]) => (
              <details key={label} open={label === "Contains" || items.length <= 6}>
                <summary>
                  {label} <span className="muted">{items.length}</span>
                </summary>
                <ul>
                  {items.slice(0, label === "Contains" ? 200 : 40).map((it) => {
                    const n = neighbors[it.id];
                    if (!n) return null;
                    return (
                      <li key={it.id}>
                        <button
                          type="button"
                          onClick={() => onNavigate(it.id)}
                          title={it.low ? "low-confidence (inferred) relation" : undefined}
                        >
                          <span className="legend-dot" style={{ background: layerColor(layers, n.layer) }} />
                          <span className="impact-name">{n.name}</span>
                          <span className="impact-sub">
                            {n.node_type}
                            {it.low ? " · inferred" : ""}
                            {it.evidence ? ` · ${tierLabel(it.evidence.tier)}` : ""}
                            {it.extractor ? ` · ${it.extractor}` : ""}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
                {items.length > (label === "Contains" ? 200 : 40) ? (
                  <p className="muted pad">
                    +{items.length - (label === "Contains" ? 200 : 40)} more · use ⌘K to find one
                  </p>
                ) : null}
              </details>
            ))}
        </div>
      ) : isContainer ? (
        <p className="muted code-empty">No indexed children under this {node.node_type.toLowerCase()}.</p>
      ) : null}
    </>
  );
}

/** "a.b.c" vs "a/b/c.py" (or a path that merely ends with it) is the same information twice. */
function sameAsPath(qualified: string, path?: string | null): boolean {
  if (!path) return false;
  const noExt = path.replace(/\.[^./]+$/, "");
  const dotted = qualified.replace(/\./g, "/");
  return qualified === path || qualified === noExt || noExt.endsWith(dotted) || noExt.endsWith(`${dotted}/__init__`);
}

function SourceView({ source, highlight }: { source: SourceSnippet | null; highlight: [number, number] | null }) {
  const [copied, setCopied] = useState(false);
  const tokens = useMemo(
    () => (source ? highlightLines(source.content.split("\n"), languageOf(source.path)) : []),
    [source],
  );
  if (!source) {
    return <p className="muted code-empty">No indexed source file for this selection.</p>;
  }
  if (!source.content.trim()) {
    return (
      <p className="muted code-empty">
        <span className="mono">{source.path}</span> is empty.
      </p>
    );
  }
  const at = highlight?.[0] ?? source.start;
  const editorHref = source.abs_path ? `vscode://file/${source.abs_path}:${at}` : undefined;
  return (
    <section className="code-block" aria-label={`Source of ${source.path}`}>
      <div className="code-header">
        <span className="mono code-path" title={source.path}>
          {source.path}
          <span className="muted">
            {" "}
            {source.start}–{source.end} of {source.total_lines}
          </span>
        </span>
        <span className="code-actions">
          <button
            type="button"
            className="icon-btn"
            title="Copy path:line"
            aria-label="Copy path and line"
            onClick={() =>
              void navigator.clipboard?.writeText(`${source.path}:${at}`).then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 1200);
              })
            }
          >
            <Copy size={14} strokeWidth={1.5} aria-hidden />
          </button>
          {copied ? <span className="muted code-copied">Copied</span> : null}
          {editorHref ? (
            <a className="icon-btn" href={editorHref} title="Open in VS Code" aria-label="Open in VS Code">
              <ExternalLink size={14} strokeWidth={1.5} aria-hidden />
            </a>
          ) : null}
        </span>
      </div>
      {/* focusable so keyboard users can scroll long lines (WCAG 2.1.1) */}
      <pre className="code-lines" tabIndex={0} aria-label={`${source.path} lines ${source.start} to ${source.end}`}>
        {tokens.map((line, i) => {
          const n = source.start + i;
          const hot = highlight && n >= highlight[0] && n <= highlight[1];
          return (
            <div key={n} className={`code-line ${hot ? "hot" : ""}`}>
              <span className="code-ln">{n}</span>
              <span className="code-text">
                {line.length === 0 || (line.length === 1 && !line[0].text) ? " " : null}
                {line.map((t, j) =>
                  t.kind ? (
                    <span key={j} className={`tk-${t.kind}`}>
                      {t.text}
                    </span>
                  ) : (
                    t.text
                  ),
                )}
              </span>
            </div>
          );
        })}
      </pre>
    </section>
  );
}
