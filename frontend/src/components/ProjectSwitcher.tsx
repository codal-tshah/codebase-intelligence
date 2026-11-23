import { ChevronDown, FolderCog, Plus, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { timeAgo } from "../indexJobs";
import type { Project, ProjectOverview } from "../types";
import { Popover } from "./Popover";

type Props = {
  projects: Project[];
  /** Richer per-project info (stats, stale), when loaded. */
  overview: ProjectOverview[] | null;
  projectId: string;
  onPick: (id: string) => void;
  onManage: () => void;
  onAdd: () => void;
  onOpen?: () => void;
};

/** Project switcher: searchable list with stats and a stale badge, plus "Manage projects". */
export function ProjectSwitcher({ projects, overview, projectId, onPick, onManage, onAdd, onOpen }: Props) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const trigger = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const byId = useMemo(() => new Map((overview ?? []).map((o) => [o.id, o])), [overview]);
  const current = projects.find((p) => p.id === projectId);
  const currentInfo = byId.get(projectId);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return projects.filter(
      (p) => !needle || p.name.toLowerCase().includes(needle) || p.root_path.toLowerCase().includes(needle),
    );
  }, [projects, q]);

  const close = useCallback((opts?: { returnFocus?: boolean }) => {
    setOpen(false);
    setQ("");
    if (opts?.returnFocus !== false) trigger.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    onOpen?.();
    setActive(
      Math.max(
        0,
        shown.findIndex((p) => p.id === projectId),
      ),
    );
    const t = setTimeout(() => input.current?.focus(), 0);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once per open
  }, [open]);

  const pick = (id: string) => {
    close();
    if (id !== projectId) onPick(id);
  };

  return (
    <>
      <button
        ref={trigger}
        type="button"
        className="project-switcher"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`Project: ${current?.name ?? "none"}. Switch project`}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="project-switcher-name">{current?.name ?? "Choose a project"}</span>
        {currentInfo?.stale ? <span className="stale-dot" title="New commits since the last index" /> : null}
        <ChevronDown size={14} strokeWidth={1.5} aria-hidden />
      </button>
      <Popover
        open={open}
        onClose={close}
        anchorRef={trigger}
        role="dialog"
        label="Switch project"
        className="project-pop"
      >
        <label className="project-pop-search">
          <Search size={14} strokeWidth={1.5} aria-hidden />
          <input
            ref={input}
            value={q}
            placeholder={`Search ${projects.length} project${projects.length === 1 ? "" : "s"}`}
            aria-label="Search projects"
            role="combobox"
            aria-expanded
            aria-controls="project-pop-list"
            aria-activedescendant={shown[active] ? `project-opt-${shown[active].id}` : undefined}
            onChange={(e) => {
              setQ(e.target.value);
              setActive(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActive((a) => Math.min(a + 1, shown.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive((a) => Math.max(a - 1, 0));
              } else if (e.key === "Enter" && shown[active]) {
                e.preventDefault();
                pick(shown[active].id);
              }
            }}
          />
        </label>
        <div className="project-pop-list" id="project-pop-list" role="listbox" aria-label="Projects">
          {shown.length === 0 ? <p className="muted pad">No project matches “{q}”.</p> : null}
          {shown.map((p, i) => {
            const info = byId.get(p.id);
            return (
              <button
                key={p.id}
                id={`project-opt-${p.id}`}
                type="button"
                role="option"
                tabIndex={-1}
                aria-selected={p.id === projectId}
                className={`popover-item project-opt ${i === active ? "active" : ""}`}
                onMouseEnter={() => setActive(i)}
                onClick={() => pick(p.id)}
              >
                <span className="project-opt-main">
                  <span className="project-opt-name">
                    {p.name}
                    {info?.stale ? <span className="badge badge-warn">new commits</span> : null}
                    {info?.indexing ? <span className="badge">indexing</span> : null}
                  </span>
                  <span className="project-opt-sub muted">
                    {info
                      ? `${info.files ?? info.stats.files ?? "?"} files · ${info.stats.endpoints ?? 0} routes · ${info.stats.models ?? 0} models · indexed ${timeAgo(info.indexed_at)}`
                      : p.root_path}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
        <div className="project-pop-foot">
          <button type="button" className="btn ghost small" onClick={() => (close({ returnFocus: false }), onManage())}>
            <FolderCog size={14} strokeWidth={1.5} aria-hidden /> Manage projects
          </button>
          <button type="button" className="btn ghost small" onClick={() => (close({ returnFocus: false }), onAdd())}>
            <Plus size={14} strokeWidth={1.5} aria-hidden /> Add repository
          </button>
        </div>
      </Popover>
    </>
  );
}
