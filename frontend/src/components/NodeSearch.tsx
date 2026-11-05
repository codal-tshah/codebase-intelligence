import { Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { getJson } from "../api";
import { NodeIcon } from "../icons";
import type { SearchHit } from "../types";

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

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as globalThis.Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const pick = (hit: SearchHit) => {
    onPick(hit);
    setOpen(false);
    setQuery(clearOnPick ? "" : hit.name);
  };

  return (
    <div className="node-search" ref={box}>
      <Search className="search-icon" size={14} strokeWidth={1.5} aria-hidden />
      <input
        id={inputId}
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
      {open && hits.length > 0 ? (
        <ul className="search-results">
          {hits.map((h, i) => (
            <li key={h.id}>
              <button
                type="button"
                className={i === active ? "active" : ""}
                onMouseEnter={() => setActive(i)}
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
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
