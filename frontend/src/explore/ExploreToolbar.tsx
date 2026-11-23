import { ArrowLeft, ChevronsLeft, Plus } from "lucide-react";
import { MenuSelect, type SelectOption } from "../components/Popover";

/** "All" levels is sent to the API as this level (its maximum). */
export const ALL_LEVELS = 64;
const MAX_LISTED = 10;

/** Level choices for the current graph: 1..min(maxDepth, 10), plus "All" when deeper. */
export function levelOptions(maxDepth: number | undefined, { includeAll }: { includeAll: boolean }): SelectOption<number>[] {
  const max = Math.max(1, maxDepth ?? 3);
  const listed = Math.min(max, MAX_LISTED);
  const out: SelectOption<number>[] = Array.from({ length: listed }, (_, i) => ({
    value: i + 1,
    label: `Level ${i + 1}`,
    hint: i === 0 ? "top packages" : undefined,
  }));
  if (includeAll) out.push({ value: ALL_LEVELS, label: "All levels", hint: `${max} deep` });
  return out;
}

type Props = {
  expandedCount: number;
  canGoBack: boolean;
  maxDepth?: number;
  /** Name of the selected expandable node: Depth then applies inside it. */
  scopeName?: string | null;
  canExpandSelection: boolean;
  busy: boolean;
  onBack: () => void;
  onReset: () => void;
  onExpandToLevel: (level: number) => void;
  onCollapseToLevel: (level: number) => void;
  onExpandSelection: () => void;
};

/** Explore controls: history, reset, open N levels (whole tree or the selected package), collapse. */
export function ExploreToolbar(p: Props) {
  return (
    <div className="canvas-toolbar-explore" role="group" aria-label="Explore controls">
      <button type="button" className="icon-btn" onClick={p.onBack} disabled={!p.canGoBack} title="Back" aria-label="Back one expand">
        <ArrowLeft size={16} strokeWidth={1.5} aria-hidden />
      </button>
      <button type="button" className="icon-btn" onClick={p.onReset} title="Reset to top level" aria-label="Reset explore">
        <ChevronsLeft size={16} strokeWidth={1.5} aria-hidden />
      </button>
      <span className="muted explore-depth">
        <span className="explore-depth-label">{p.scopeName ? "Open in selection" : "Open to"}</span>
        <MenuSelect
          label={p.scopeName ? `Open levels inside ${p.scopeName}` : "Open the tree to level"}
          title={p.scopeName ? `Expand ${p.scopeName} down to a level` : "Expand every package down to a level"}
          value={null}
          placeholder={p.scopeName ? "Open inside…" : "Open level…"}
          disabled={p.busy}
          onChange={p.onExpandToLevel}
          options={levelOptions(p.maxDepth, { includeAll: true })}
        />
      </span>
      <span className="muted explore-depth">
        <span className="explore-depth-label">Collapse to</span>
        <MenuSelect
          label="Collapse the tree to level"
          value={null}
          placeholder="Collapse…"
          disabled={p.busy || p.expandedCount === 0}
          onChange={p.onCollapseToLevel}
          options={levelOptions(Math.max(1, (p.maxDepth ?? 3) - 1), { includeAll: false })}
        />
      </span>
      <button
        type="button"
        className="icon-btn"
        onClick={p.onExpandSelection}
        disabled={!p.canExpandSelection}
        title="Expand the selection one level"
        aria-label="Expand the selection one level"
      >
        <Plus size={16} strokeWidth={1.5} aria-hidden />
      </button>
    </div>
  );
}
