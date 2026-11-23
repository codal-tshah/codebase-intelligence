import { BaseEdge, getBezierPath, type Edge, type EdgeProps } from "@xyflow/react";
import { memo } from "react";
import type { EdgeData } from "../flow";

type P = { x: number; y: number };

/**
 * Orthogonal path through ELK's bend points, with the first/last horizontal runs snapped to the
 * React Flow handles (ELK may attach a few pixels off the handle centre). Corners are rounded.
 * Exported for tests.
 */
export function orthogonalPath(
  points: P[],
  sx: number,
  sy: number,
  tx: number,
  ty: number,
  radius = 6,
): { path: string; label: P } {
  const inner = points.slice(1, -1).map((p) => ({ ...p }));
  if (inner.length >= 2) {
    inner[0].y = sy;
    inner[inner.length - 1].y = ty;
  }
  let pts: P[] = [{ x: sx, y: sy }, ...inner, { x: tx, y: ty }];
  if (inner.length < 2 && Math.abs(sy - ty) > 0.5) {
    const mx = (sx + tx) / 2;
    pts = [
      { x: sx, y: sy },
      { x: mx, y: sy },
      { x: mx, y: ty },
      { x: tx, y: ty },
    ];
  }
  let d = `M${pts[0].x},${pts[0].y}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const a = pts[i - 1];
    const b = pts[i];
    const c = pts[i + 1];
    const r = Math.min(radius, Math.hypot(b.x - a.x, b.y - a.y) / 2, Math.hypot(c.x - b.x, c.y - b.y) / 2);
    const ux = Math.sign(b.x - a.x);
    const uy = Math.sign(b.y - a.y);
    const vx = Math.sign(c.x - b.x);
    const vy = Math.sign(c.y - b.y);
    d += ` L${b.x - ux * r},${b.y - uy * r} Q${b.x},${b.y} ${b.x + vx * r},${b.y + vy * r}`;
  }
  const last = pts[pts.length - 1];
  d += ` L${last.x},${last.y}`;
  // label on the middle segment
  const m = Math.floor((pts.length - 1) / 2);
  const label = { x: (pts[m].x + pts[m + 1].x) / 2, y: (pts[m].y + pts[m + 1].y) / 2 };
  return { path: d, label };
}

function RoutedEdgeBase(props: EdgeProps<Edge<EdgeData>>) {
  const {
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    data,
    markerEnd,
    style,
    label,
    labelStyle,
    labelBgStyle,
    labelBgPadding,
    interactionWidth,
  } = props;
  const points = data?.points;
  let path: string;
  let lx: number;
  let ly: number;
  if (points && points.length >= 2) {
    const r = orthogonalPath(points, sourceX, sourceY, targetX, targetY);
    path = r.path;
    lx = r.label.x;
    ly = r.label.y;
  } else {
    [path, lx, ly] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
  }
  return (
    <BaseEdge
      path={path}
      markerEnd={markerEnd}
      style={style}
      label={label}
      labelX={lx}
      labelY={ly}
      labelStyle={labelStyle}
      labelBgStyle={labelBgStyle}
      labelBgPadding={labelBgPadding}
      interactionWidth={interactionWidth}
    />
  );
}

export const RoutedEdge = memo(RoutedEdgeBase);
