import { ACCENT, EXPLORE_DOWNSTREAM, EXPLORE_UPSTREAM } from "../graphTheme";

const ROWS: { label: string; color: string; dashed?: boolean; title: string }[] = [
  { label: "Calls, routes, reads", color: "#9A958A", title: "Statically resolved relation" },
  { label: "Imports, handles", color: "#B5B0A5", dashed: true, title: "Structural relation" },
  {
    label: "Inferred",
    color: "#9A958A",
    dashed: true,
    title: "Heuristic match (confidence below 70%): verify in source",
  },
  { label: "HTTP from the UI", color: ACCENT, title: "Frontend request linked to a backend route" },
  {
    label: "In: depends on selection",
    color: EXPLORE_UPSTREAM,
    title: "Upstream of the selected node (its callers, importers, routes into it)",
  },
  {
    label: "Out: selection depends on",
    color: EXPLORE_DOWNSTREAM,
    title: "Downstream of the selected node (what it calls, imports, reads)",
  },
];

/** Key for edge strokes so dashed (inferred / structural) lines aren't guesswork. */
export function EdgeLegend() {
  return (
    <div className="legend">
      <p className="sidebar-label">Edges</p>
      <ul className="edge-legend">
        {ROWS.map((r) => (
          <li key={r.label} title={r.title}>
            <svg width="28" height="8" aria-hidden>
              <line
                x1="0"
                y1="4"
                x2="28"
                y2="4"
                stroke={r.color}
                strokeWidth="1.5"
                strokeDasharray={r.dashed ? "5 4" : undefined}
              />
            </svg>
            {r.label}
          </li>
        ))}
        <li title="Nodes found by heuristics are outlined dashed">
          <svg width="28" height="12" aria-hidden>
            <rect x="1" y="1" width="26" height="10" rx="3" fill="none" stroke="#9A958A" strokeDasharray="4 3" />
          </svg>
          Inferred node
        </li>
      </ul>
    </div>
  );
}
