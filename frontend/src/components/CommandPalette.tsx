import { CornerDownLeft, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getJson } from "../api";
import { NodeIcon, ViewIcon } from "../icons";
import type { SearchHit, ViewInfo } from "../types";

export type PaletteAction = { id: string; label: string; hint?: string; icon?: ReactNode; run: () => void };

type Item =
  | { kind: "node"; key: string; hit: SearchHit }
  | { kind: "view"; key: string; view: ViewInfo }
  | { kind: "action"; key: string; action: PaletteAction };

type Props = {
  open: boolean;
  projectId: string;
  views: ViewInfo[];
  actions: PaletteAction[];
  onClose: () => void;
  onPickNode: (hit: SearchHit) => void;
  onPickView: (id: string) => void;
};

/** ⌘K: one place to find code, switch views, and run actions. */
export function CommandPalette({ open, projectId, views, actions, onClose, onPickNode, onPickView }: Props) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setHits([]);
      setActive(0);
      requestAnimationFrame(() => input.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    const q = query.trim();
    if (!open || !projectId || q.length < 2) {
      setHits([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    const t = setTimeout(() => {
      getJson<{ results: SearchHit[] }>(`/projects/${projectId}/search?${new URLSearchParams({ q, limit: "8" })}`)
        .then((r) => setHits(r.results))
        .catch(() => setHits([]))
        .finally(() => setSearching(false));
    }, 140);
    return () => clearTimeout(t);
  }, [query, open, projectId]);

  const items = useMemo<Item[]>(() => {
    const q = query.trim().toLowerCase();
    const match = (s: string) => !q || s.toLowerCase().includes(q);
    return [
      ...hits.map((hit) => ({ kind: "node" as const, key: `n:${hit.id}`, hit })),
      ...views.filter((v) => v.available && match(v.label)).map((view) => ({ kind: "view" as const, key: `v:${view.id}`, view })),
      ...actions.filter((a) => match(a.label)).map((action) => ({ kind: "action" as const, key: `a:${action.id}`, action })),
    ];
  }, [hits, views, actions, query]);

  useEffect(() => setActive((a) => Math.min(a, Math.max(items.length - 1, 0))), [items.length]);
  useEffect(() => {
    list.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  if (!open) return null;

  const run = (item: Item | undefined) => {
    if (!item) return;
    onClose();
    if (item.kind === "node") onPickNode(item.hit);
    else if (item.kind === "view") onPickView(item.view.id);
    else item.action.run();
  };

  let lastKind: Item["kind"] | null = null;
  const heading: Record<Item["kind"], string> = { node: "Code", view: "Go to", action: "Actions" };

  return (
    <div className="palette-backdrop" onMouseDown={onClose}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette" onMouseDown={(e) => e.stopPropagation()}>
        <div className="palette-input">
          <Search size={16} strokeWidth={1.5} aria-hidden />
          <input
            ref={input}
            value={query}
            placeholder="Search code, or jump to a view or action…"
            aria-label="Search"
            aria-controls="palette-list"
            aria-activedescendant={items[active] ? `palette-${active}` : undefined}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActive((a) => Math.min(a + 1, items.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive((a) => Math.max(a - 1, 0));
              } else if (e.key === "Enter") {
                e.preventDefault();
                run(items[active]);
              } else if (e.key === "Escape") {
                e.preventDefault();
                onClose();
              }
            }}
          />
          <kbd>esc</kbd>
        </div>
        <ul className="palette-list" id="palette-list" role="listbox" ref={list}>
          {searching && hits.length === 0 ? (
            <li className="palette-status">
              <span className="skeleton" style={{ width: "40%" }} />
            </li>
          ) : null}
          {!searching && items.length === 0 ? (
            <li className="palette-status muted">No matches. Try a function, route, file or model name.</li>
          ) : null}
          {items.map((item, i) => {
            const head = item.kind !== lastKind ? heading[item.kind] : null;
            lastKind = item.kind;
            return (
              <li key={item.key} role="presentation">
                {head ? <p className="palette-heading">{head}</p> : null}
                <button
                  type="button"
                  role="option"
                  id={`palette-${i}`}
                  data-index={i}
                  aria-selected={i === active}
                  className={`palette-item ${i === active ? "active" : ""}`}
                  onMouseMove={() => setActive(i)}
                  onClick={() => run(item)}
                >
                  {item.kind === "node" ? (
                    <>
                      <NodeIcon type={item.hit.node_type} size={16} />
                      <span className="palette-main">
                        <span className="palette-label">{item.hit.name}</span>
                        <span className="palette-sub mono">{item.hit.source_path ?? item.hit.node_type}</span>
                      </span>
                    </>
                  ) : item.kind === "view" ? (
                    <>
                      <ViewIcon id={item.view.id} />
                      <span className="palette-main">
                        <span className="palette-label">{item.view.label}</span>
                        <span className="palette-sub">{item.view.description}</span>
                      </span>
                    </>
                  ) : (
                    <>
                      {item.action.icon ?? <CornerDownLeft size={16} strokeWidth={1.5} aria-hidden />}
                      <span className="palette-main">
                        <span className="palette-label">{item.action.label}</span>
                      </span>
                      {item.action.hint ? <kbd>{item.action.hint}</kbd> : null}
                    </>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
