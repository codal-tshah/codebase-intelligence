import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { memo } from "react";
import type { ArchNodeData } from "../flow";
import { NodeIcon } from "../icons";

const LAYER_LABEL: Record<string, string> = { api: "API", ui: "UI" };
const label = (id?: string | null) => (id ? (LAYER_LABEL[id] ?? id[0].toUpperCase() + id.slice(1)) : null);

function ArchNodeBase({ data }: NodeProps<Node<ArchNodeData>>) {
  const ring = data.ring;
  const layer = label(data.layer);
  return (
    <div
      className={`arch-node arch-node--${data.state}`}
      style={{ ["--layer" as string]: data.color, ...(ring ? { ["--ring" as string]: ring } : {}) }}
      title={data.summary ?? undefined}
    >
      <Handle type="target" position={Position.Left} className="arch-handle" />
      <div className="arch-node-top">
        <span className="arch-node-type">
          <NodeIcon type={data.nodeType} size={12} />
          {data.nodeType}
          {layer ? <span className="arch-node-layer">{layer}</span> : null}
        </span>
        {data.fanIn > 0 ? (
          <span className="arch-node-meta" title={`${data.fanIn} dependants · ${data.fanOut} dependencies`}>
            {data.fanIn} in
          </span>
        ) : null}
      </div>
      <div className="arch-node-name" title={data.label}>
        {data.label}
      </div>
      {data.memberCount !== undefined ? (
        <div className="arch-node-path">{data.memberCount} members</div>
      ) : data.path ? (
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
      {data.badge ? <span className="arch-badge">{data.badge}</span> : null}
      <Handle type="source" position={Position.Right} className="arch-handle" />
    </div>
  );
}

export const ArchNode = memo(ArchNodeBase);
