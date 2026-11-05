import type { Freshness } from "../types";

type Props = {
  freshness: Freshness | null;
  busy: boolean;
  onReindex: () => void;
  onShowImpact: () => void;
};

const LABEL: Record<Freshness["status"], string> = {
  fresh: "Index is current",
  dirty: "Uncommitted changes",
  stale: "Index is out of date",
  unknown: "Not indexed",
};

export function FreshnessBanner({ freshness, busy, onReindex, onShowImpact }: Props) {
  if (!freshness || freshness.status === "fresh") return null;
  const count = freshness.changed_count ?? freshness.changed_files.length;
  return (
    <div className={`freshness freshness--${freshness.status}`} role="status">
      <span className="freshness-dot" aria-hidden />
      <div className="freshness-copy">
        <strong>{LABEL[freshness.status]}</strong>
        <span>
          {freshness.message}
          {freshness.changed_files.length > 0
            ? ` (${freshness.changed_files.slice(0, 3).join(", ")}${count > 3 ? ` +${count - 3} more` : ""})`
            : ""}
        </span>
      </div>
      {count > 0 ? (
        <button type="button" className="btn ghost small" onClick={onShowImpact}>
          Show impact
        </button>
      ) : null}
      <button type="button" className="btn primary small" onClick={onReindex} disabled={busy}>
        {busy ? "Re-indexing…" : "Re-index now"}
      </button>
    </div>
  );
}
