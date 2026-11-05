import { LAYER_COLORS } from "../graphTheme";
import type { Layer } from "../types";

type Props = {
  layers: Layer[];
  hidden: Set<string>;
  onToggle: (id: string) => void;
};

/** Layer colour key that doubles as a visibility filter. */
export function LayerLegend({ layers, hidden, onToggle }: Props) {
  if (layers.length === 0) return null;
  return (
    <div className="legend">
      <p className="sidebar-label">Layers</p>
      <ul>
        {layers.map((l) => {
          const off = hidden.has(l.id);
          return (
            <li key={l.id}>
              <button
                type="button"
                className={`legend-item ${off ? "off" : ""}`}
                onClick={() => onToggle(l.id)}
                title={l.description || `Toggle ${l.name}`}
              >
                <span className="legend-dot" style={{ background: LAYER_COLORS[l.id] ?? l.color }} />
                <span className="legend-name">{l.name}</span>
                {l.count !== undefined ? <span className="legend-count">{l.count}</span> : null}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
