import type { Edge, Node } from "@xyflow/react";
import { Download } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiFetch, saveBlob } from "../api";
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
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as globalThis.Node)) setOpen(false);
    };
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", close);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", close);
    };
  }, [open]);

  const base = safeFilename(projectName, viewLabel);
  const meta = { project: projectName, view: viewLabel };
  const run = async (fn: () => Promise<void> | void) => {
    setError(null);
    try {
      await fn();
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    }
  };
  const text = (content: string, ext: string, type: string) => saveBlob(new Blob([content], { type }), `${base}.${ext}`);

  const items: { label: string; hint: string; disabled?: boolean; run: () => Promise<void> | void }[] = [
    { label: "SVG image", hint: ".svg", disabled: !nodes.length, run: () => text(toSvg(nodes, edges), "svg", "image/svg+xml") },
    { label: "PNG image", hint: ".png", disabled: !nodes.length, run: async () => saveBlob(await svgToPng(toSvg(nodes, edges)), `${base}.png`) },
    { label: "Mermaid diagram", hint: ".mmd", disabled: !payload, run: () => payload && text(toMermaid(payload, `${projectName} — ${viewLabel}`), "mmd", "text/plain") },
    { label: "Markdown report", hint: ".md", disabled: !payload, run: () => payload && text(toMarkdown(payload, meta), "md", "text/markdown") },
    { label: "This view as JSON", hint: ".json", disabled: !payload, run: () => payload && text(toJson(payload, meta), "json", "application/json") },
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
    <div className="export-menu" ref={ref}>
      <button
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
      {open ? (
        <ul className="export-menu-list" role="menu" aria-label="Export formats">
          {items.map((it) => (
            <li key={it.label} role="none">
              <button type="button" role="menuitem" disabled={it.disabled} onClick={() => void run(it.run)}>
                <span>{it.label}</span>
                <span className="muted mono">{it.hint}</span>
              </button>
            </li>
          ))}
          {error ? (
            <li role="alert" className="form-error pad">
              {error}
            </li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
