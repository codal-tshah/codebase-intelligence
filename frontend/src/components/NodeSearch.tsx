import { Search } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { getJson } from "../api";
import { NodeIcon } from "../icons";
import type { SearchHit } from "../types";
import { Popover } from "./Popover";

type Props = {
  projectId: string;
  placeholder?: string;
  onPick: (hit: SearchHit) => void;
  types?: string;
  clearOnPick?: boolean;
  initial?: string;
  inputId?: string;
};

/** Server-side fuzzy search (names, paths, tags, summaries) with a keyboard-friendly dropdown. */
export function NodeSearch({ projectId, placeholder, onPick, types, clearOnPick = true, initial = "", inputId }: Props) {
  const [query, setQuery] = useState(initial);
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    const q = query.trim();
    if (!projectId || q.length < 2) {
      setHits([]);
      return;
    }
    const handle = setTimeout(() => {
      const params = new URLSearchParams({ q, limit: "8" });
      if (types) params.set("types", types);
      getJson<{ results: SearchHit[] }>(`/projects/${projectId}/search?${params}`)
        .then((r) => {
          setHits(r.results);
          setActive(0);
        })
        .catch(() => setHits([]));
    }, 180);
    return () => clearTimeout(handle);
  }, [query, projectId, types]);

  const pick = (hit: SearchHit) => {
    onPick(hit);
    setOpen(false);
    setQuery(clearOnPick ? "" : hit.name);
  };

  return (
    <div className="node-search" ref={box}>
      <Search className="search-icon" size={14} strokeWidth={1.5} aria-hidden />
      <input
        ref={input}
        id={inputId}
        role="combobox"
        aria-expanded={open && hits.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && hits[active] ? `${listId}-${active}` : undefined}
        value={query}
        placeholder={placeholder ?? "Search symbols, routes, files…"}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(a + 1, hits.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter" && hits[active]) {
            e.preventDefault();
            pick(hits[active]);
          } else if (e.key === "Escape") {
            setOpen(false);
            (e.target as HTMLInputElement).blur();
          }
        }}
      />
      <Popover open={open && hits.length > 0} onClose={close} anchorRef={box} matchWidth role="listbox" id={listId} label="Search results" className="search-results">
          {hits.map((h, i) => (
              <button
                key={h.id}
                id={`${listId}-${i}`}
                type="button"
                role="option"
                tabIndex={-1}
                aria-selected={i === active}
                className={`popover-item ${i === active ? "active" : ""}`}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(h)}
              >
                <span className="search-hit-glyph"><NodeIcon type={h.node_type} /></span>
                <span className="search-hit-main">
                  <span className="search-hit-name">{h.name}</span>
                  <span className="search-hit-sub">
                    {h.node_type}
                    {h.source_path ? ` · ${h.source_path}` : ""}
                  </span>
                </span>
              </button>
          ))}
      </Popover>
    </div>
  );
}
