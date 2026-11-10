import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { type KeyboardEvent, memo, useRef } from "react";
import type { ArchNodeData } from "../flow";
import { NodeIcon } from "../icons";

const LAYER_LABEL: Record<string, string> = { api: "API", ui: "UI" };
const layerLabel = (id?: string | null) => (id ? (LAYER_LABEL[id] ?? id[0].toUpperCase() + id.slice(1)) : null);

function ArchNodeBase({ data, selected }: NodeProps<Node<ArchNodeData>>) {
  const ring = data.ring;
  const layer = layerLabel(data.layer);
  const exploreGroup = Boolean(data.exploreGroup);
  const chevronRef = useRef<HTMLButtonElement>(null);
  const expandable = Boolean(data.exploreExpandable);
  const expanded = Boolean(data.exploreExpanded);

  const onKeyDown = (e: KeyboardEvent) => {
    if (!expandable) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      data.onExploreChevronClick?.();
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      if (expanded) data.onExploreChevronClick?.();
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      if (!expanded) data.onExploreChevronClick?.();
    }
  };

  const body = (
    <>
      <div className="arch-node-top">
        <span className="arch-node-type">
          <NodeIcon type={data.nodeType} size={12} />
          {data.nodeType}
          {layer ? <span className="arch-node-layer">{layer}</span> : null}
        </span>
        <span className="arch-node-top-right">
          {data.fanIn > 0 ? (
            <span className="arch-node-meta" title={`${data.fanIn} dependants · ${data.fanOut} dependencies`}>
              {data.fanIn} in
            </span>
          ) : null}
          {expandable ? (
            <button
              ref={chevronRef}
              type="button"
              className="arch-chevron"
              aria-label={expanded ? "Collapse" : "Expand"}
              aria-expanded={expanded}
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                data.onExploreChevronClick?.();
              }}
            >
              {expanded ? <ChevronDown size={16} strokeWidth={1.5} aria-hidden /> : <ChevronRight size={16} strokeWidth={1.5} aria-hidden />}
            </button>
          ) : null}
        </span>
      </div>
      <div className="arch-node-name" title={data.label}>
        {data.label}
      </div>
      {exploreGroup && data.exploreChildCount !== undefined ? (
        <div className="arch-node-explore-meta muted">
          {data.exploreChildCount} {data.exploreChildCount === 1 ? "child" : "children"}
        </div>
      ) : null}
      {data.memberCount !== undefined ? (
        <div className="arch-node-path">{data.memberCount} members</div>
      ) : data.path && !exploreGroup ? (
        <div className="arch-node-path" title={data.path}>
          {data.path}
        </div>
      ) : null}
      {data.fields && data.fields.length > 0 ? (
        <ul className="arch-fields">
          {data.fields.slice(0, 12).map((f) => (
            <li key={f.name}>
              <span>{f.name}</span>
              <em>{f.relation ? `→ ${f.relation}` : f.type.replace("Field", "")}</em>
            </li>
          ))}
          {data.fields.length > 12 ? <li className="muted">+{data.fields.length - 12} more</li> : null}
        </ul>
      ) : null}
      {Number(data.truncatedChildren ?? 0) > 0 ? (
        <button
          type="button"
          className="arch-more-chip"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            data.onExploreLoadMore?.();
          }}
        >
          +{data.truncatedChildren} more
        </button>
      ) : null}
      {data.exploreLoading ? <span className="arch-loading-dot" aria-busy title="Loading" /> : null}
      {data.badge && !expandable ? <span className="arch-badge">{data.badge}</span> : null}
    </>
  );

  return (
    <div
      className={`arch-node arch-node--${data.state}${exploreGroup ? " arch-node--explore-group" : ""}`}
      style={{ ["--layer" as string]: data.color, ...(ring ? { ["--ring" as string]: ring } : {}) }}
      title={data.summary ?? undefined}
      tabIndex={selected && expandable ? 0 : -1}
      onKeyDown={onKeyDown}
    >
      <Handle type="target" position={Position.Left} className="arch-handle" />
      {body}
      <Handle type="source" position={Position.Right} className="arch-handle" />
    </div>
  );
}

export const ArchNode = memo(ArchNodeBase);

/** Column header for the Layers view (direct label instead of a legend). */
export const LaneLabel = memo(function LaneLabel({ data }: NodeProps<Node<Record<string, unknown>>>) {
  return (
    <div className="lane-label" style={{ ["--layer" as string]: String(data.color ?? "#8A867C") }}>
      <span className="lane-dot" aria-hidden />
      {String(data.label)}
      <span className="lane-count">{String(data.count ?? "")}</span>
    </div>
  );
});
