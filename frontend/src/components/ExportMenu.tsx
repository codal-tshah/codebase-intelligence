import type { Edge, Node } from "@xyflow/react";
import { Download } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, saveBlob } from "../api";
import { Popover, usePopoverKeys } from "./Popover";
import { safeFilename, svgToPng, toJson, toMarkdown, toMermaid, toSvg } from "../export/exportView";
import type { ArchNodeData } from "../flow";
import type { GraphPayload } from "../types";

type Props = {
  projectId: string;
  projectName: string;
  viewLabel: string;
  payload: GraphPayload | null;
  nodes: Node<ArchNodeData>[];
  edges: Edge[];
};

/** Export the current view (client-side) or the full graph (server JSON). */
export function ExportMenu({ projectId, projectName, viewLabel, payload, nodes, edges }: Props) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const keys = usePopoverKeys();
  const close = useCallback((opts?: { returnFocus?: boolean }) => {
    setOpen(false);
    if (opts?.returnFocus !== false) trigger.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(
      () => document.querySelector<HTMLElement>(".export-menu-list [data-pop-item]:not([disabled])")?.focus(),
      0,
    );
    return () => clearTimeout(t);
  }, [open]);

  const base = safeFilename(projectName, viewLabel);
  const meta = { project: projectName, view: viewLabel };
  const run = async (fn: () => Promise<void> | void) => {
    setError(null);
    try {
      await fn();
      close();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    }
  };
  const text = (content: string, ext: string, type: string) =>
    saveBlob(new Blob([content], { type }), `${base}.${ext}`);

  const items: { label: string; hint: string; disabled?: boolean; run: () => Promise<void> | void }[] = [
    {
      label: "SVG image",
      hint: ".svg",
      disabled: !nodes.length,
      run: () => text(toSvg(nodes, edges), "svg", "image/svg+xml"),
    },
    {
      label: "PNG image",
      hint: ".png",
      disabled: !nodes.length,
      run: async () => saveBlob(await svgToPng(toSvg(nodes, edges)), `${base}.png`),
    },
    {
      label: "Mermaid diagram",
      hint: ".mmd",
      disabled: !payload,
      run: () => payload && text(toMermaid(payload, `${projectName} — ${viewLabel}`), "mmd", "text/plain"),
    },
    {
      label: "Markdown report",
      hint: ".md",
      disabled: !payload,
      run: () => payload && text(toMarkdown(payload, meta), "md", "text/markdown"),
    },
    {
      label: "This view as JSON",
      hint: ".json",
      disabled: !payload,
      run: () => payload && text(toJson(payload, meta), "json", "application/json"),
    },
    {
      label: "Full graph as JSON",
      hint: "all nodes",
      disabled: !projectId,
      run: async () => {
        const res = await apiFetch(`/projects/${projectId}/export`);
        if (!res.ok) throw new Error(`Export failed (${res.status})`);
        saveBlob(await res.blob(), `${safeFilename(projectName)}-graph.json`);
      },
    },
  ];

  return (
    <div className="export-menu">
      <button
        ref={trigger}
        type="button"
        className="icon-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        title="Export this view"
        aria-label="Export this view"
        onClick={() => setOpen((o) => !o)}
      >
        <Download size={16} strokeWidth={1.5} aria-hidden />
      </button>
      <Popover
        open={open}
        onClose={close}
        anchorRef={trigger}
        placement="bottom-end"
        role="menu"
        label="Export formats"
        className="export-menu-list"
        onKeyDown={keys}
      >
        {items.map((it) => (
          <button
            key={it.label}
            type="button"
            role="menuitem"
            data-pop-item
            className="popover-item"
            disabled={it.disabled}
            onClick={() => void run(it.run)}
          >
            <span>{it.label}</span>
            <span className="muted mono popover-hint">{it.hint}</span>
          </button>
        ))}
        {error ? (
          <p role="alert" className="form-error pad">
            {error}
          </p>
        ) : null}
      </Popover>
    </div>
  );
}
