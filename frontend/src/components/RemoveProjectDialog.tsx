import { AlertTriangle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { getJson, sendJson } from "../api";
import type { ProjectOverview, RemovalPlan } from "../types";

type Props = {
  project: ProjectOverview;
  onCancel: () => void;
  onRemoved: (id: string) => void;
};

/** Confirm removal, stating exactly what is deleted and that the source folder is never touched. */
export function RemoveProjectDialog({ project, onCancel, onRemoved }: Props) {
  const [plan, setPlan] = useState<RemovalPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    getJson<RemovalPlan>(`/projects/${project.id}/removal-plan`)
      .then(setPlan)
      .catch((e: Error) => setError(e.message));
    cancelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [project.id, onCancel]);

  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await sendJson("DELETE", `/projects/${project.id}`);
      onRemoved(project.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove the project");
      setBusy(false);
    }
  };

  return (
    <div
      className="palette-backdrop"
      role="presentation"
      onMouseDown={(e) => e.target === e.currentTarget && onCancel()}
    >
      <div
        className="auth-dialog confirm-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="rm-title"
        aria-describedby="rm-desc"
      >
        <h2 id="rm-title">
          <AlertTriangle size={18} strokeWidth={1.5} aria-hidden /> Remove {project.name}?
        </h2>
        <div id="rm-desc">
          {!plan && !error ? <p className="muted">Checking what would be removed…</p> : null}
          {plan ? (
            <>
              <p>This permanently deletes, from this tool's data folder:</p>
              <ul className="rm-list">
                <li>
                  <strong>Index data</strong> (graph, search index, settings, saved views)
                  <code>{plan.index_data}</code>
                </li>
                {plan.managed_clone ? (
                  <li>
                    <strong>The clone this tool made</strong> for {project.git_url ?? "the repository"}
                    <code>{plan.managed_clone}</code>
                  </li>
                ) : null}
              </ul>
              {plan.source_untouched ? (
                <p className="rm-safe">
                  Your source folder is <strong>never touched</strong>: <code>{plan.source_untouched}</code>
                </p>
              ) : (
                <p className="rm-safe">
                  The original repository on GitHub is not affected; you can add it again later.
                </p>
              )}
              {plan.indexing ? (
                <p className="form-error">An index job is running. Wait for it to finish, then remove.</p>
              ) : null}
            </>
          ) : null}
          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}
        </div>
        <div className="auth-actions">
          <button ref={cancelRef} type="button" className="btn ghost" onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className="btn danger"
            onClick={() => void remove()}
            disabled={!plan || plan.indexing || busy}
          >
            {busy ? "Removing…" : "Remove project"}
          </button>
        </div>
      </div>
    </div>
  );
}
