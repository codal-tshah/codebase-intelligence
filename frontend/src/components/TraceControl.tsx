import { ArrowLeftToLine, ArrowRightFromLine, ArrowLeftRight, X } from "lucide-react";
import { EXPLORE_DOWNSTREAM, EXPLORE_UPSTREAM } from "../graphTheme";
import { TRACE_DEPTHS, type TraceDirection, type TraceSettings } from "../trace";
import { MenuSelect } from "./Popover";

type Props = {
  value: TraceSettings;
  onChange: (next: TraceSettings) => void;
  selectedName?: string;
  /** Nodes highlighted upstream / downstream (shown as counts). */
  counts?: { up: number; down: number };
  onClear: () => void;
};

const DIRECTIONS: { id: TraceDirection; label: string; title: string; icon: JSX.Element }[] = [
  {
    id: "up",
    label: "In",
    title: "Upstream: what depends on the selection (callers, importers)",
    icon: <ArrowLeftToLine size={14} strokeWidth={1.5} aria-hidden />,
  },
  {
    id: "both",
    label: "Both",
    title: "Both directions",
    icon: <ArrowLeftRight size={14} strokeWidth={1.5} aria-hidden />,
  },
  {
    id: "down",
    label: "Out",
    title: "Downstream: what the selection depends on",
    icon: <ArrowRightFromLine size={14} strokeWidth={1.5} aria-hidden />,
  },
];

/** Trace the selection's dependencies N hops upstream, downstream or both (all graph views). */
export function TraceControl({ value, onChange, selectedName, counts, onClear }: Props) {
  return (
    <div className="trace-bar" role="group" aria-label="Trace dependencies of the selection">
      <span className="trace-title" title={selectedName}>
        Trace
      </span>
      <div className="segmented" role="radiogroup" aria-label="Trace direction">
        {DIRECTIONS.map((d) => (
          <button
            key={d.id}
            type="button"
            role="radio"
            aria-checked={value.direction === d.id}
            className={value.direction === d.id ? "active" : ""}
            title={d.title}
            onClick={() => onChange({ ...value, direction: d.id })}
          >
            {d.icon}
            {d.label}
          </button>
        ))}
      </div>
      <MenuSelect
        label="Trace depth"
        title="How many hops to follow"
        value={Number.isFinite(value.depth) ? value.depth : 999}
        onChange={(d) => onChange({ ...value, depth: d === 999 ? Infinity : d })}
        options={[
          ...TRACE_DEPTHS.map((d) => ({ value: d, label: `${d} hop${d > 1 ? "s" : ""}` })),
          { value: 999, label: "All hops" },
        ]}
      />
      {counts ? (
        <span className="trace-counts">
          {value.direction !== "down" ? (
            <span
              className="trace-key"
              style={{ ["--trace" as string]: EXPLORE_UPSTREAM }}
              title="Upstream nodes on the canvas"
            >
              {counts.up} in
            </span>
          ) : null}
          {value.direction !== "up" ? (
            <span
              className="trace-key"
              style={{ ["--trace" as string]: EXPLORE_DOWNSTREAM }}
              title="Downstream nodes on the canvas"
            >
              {counts.down} out
            </span>
          ) : null}
        </span>
      ) : null}
      <button
        type="button"
        className="icon-btn small"
        onClick={onClear}
        title="Clear selection (Esc)"
        aria-label="Clear selection"
      >
        <X size={14} strokeWidth={1.5} aria-hidden />
      </button>
    </div>
  );
}
