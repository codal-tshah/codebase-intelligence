import { Bookmark, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { getJson, postJson, sendJson } from "../api";
import type { SavedView } from "../types";
import { Popover } from "./Popover";

type Props = {
  projectId: string;
  /** Current deep-link state (same keys as the URL hash). */
  current: () => Record<string, string | undefined>;
  describe: string;
};

/** Saved views: name the current diagram + selection + expansions and come back to it later.
 * Stored per project on the server, so a saved view works for everyone using this instance. */
export function SavedViewsMenu({ projectId, current, describe }: Props) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<SavedView[] | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  const close = useCallback((opts?: { returnFocus?: boolean }) => {
    setOpen(false);
    if (opts?.returnFocus !== false) trigger.current?.focus();
  }, []);

  useEffect(() => {
    if (!open || !projectId) return;
    setError(null);
    setName(describe);
    getJson<{ views: SavedView[] }>(`/projects/${projectId}/saved-views`)
      .then((r) => setItems(r.views))
      .catch((e: Error) => setError(e.message));
  }, [open, projectId, describe]);

  const save = async () => {
    try {
      const state = Object.fromEntries(Object.entries(current()).filter(([, v]) => v)) as Record<string, string>;
      const v = await postJson<SavedView>(`/projects/${projectId}/saved-views`, {
        name: name.trim() || describe,
        state,
      });
      setItems((list) => [...(list ?? []), v]);
      setName("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    }
  };

  const openView = (v: SavedView) => {
    const params = new URLSearchParams({ p: projectId, ...v.state });
    close({ returnFocus: false });
    window.location.hash = `#/${params.toString()}`; // applied by the dashboard's hashchange handler
  };

  return (
    <>
      <button
        ref={trigger}
        type="button"
        className="icon-btn"
        aria-haspopup="dialog"
        aria-expanded={open}
        title="Saved views"
        aria-label="Saved views"
        onClick={() => setOpen((o) => !o)}
      >
        <Bookmark size={16} strokeWidth={1.5} aria-hidden />
      </button>
      <Popover
        open={open}
        onClose={close}
        anchorRef={trigger}
        placement="bottom-end"
        role="dialog"
        label="Saved views"
        className="saved-pop"
      >
        <form
          className="saved-form"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <label className="sr-only" htmlFor="saved-name">
            Name for this view
          </label>
          <input
            id="saved-name"
            value={name}
            maxLength={120}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name this view"
          />
          <button type="submit" className="btn primary small">
            Save
          </button>
        </form>
        {error ? (
          <p className="form-error pad" role="alert">
            {error}
          </p>
        ) : null}
        {items === null && !error ? <p className="muted pad">Loading…</p> : null}
        {items && items.length === 0 ? (
          <p className="muted pad">No saved views yet. Save the current diagram, selection and expansions.</p>
        ) : null}
        {items?.map((v) => (
          <div key={v.id} className="saved-row">
            <button type="button" className="popover-item" data-pop-item onClick={() => openView(v)}>
              <span>{v.name}</span>
              <span className="muted popover-hint">{v.state.v ?? ""}</span>
            </button>
            <button
              type="button"
              className="icon-btn small"
              aria-label={`Delete saved view ${v.name}`}
              onClick={async () => {
                try {
                  await sendJson("DELETE", `/projects/${projectId}/saved-views/${v.id}`);
                  setItems((list) => (list ?? []).filter((x) => x.id !== v.id));
                } catch (e) {
                  setError(e instanceof Error ? e.message : "Could not delete");
                }
              }}
            >
              <Trash2 size={13} strokeWidth={1.5} aria-hidden />
            </button>
          </div>
        ))}
      </Popover>
    </>
  );
}
