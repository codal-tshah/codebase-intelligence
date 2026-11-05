import { useEffect, useState } from "react";
import { getJson } from "../api";
import { layerColor } from "../graphTheme";
import type { Layer, TourStep } from "../types";

type Props = {
  projectId: string;
  layers: Layer[];
  activeStep: number | null;
  onSelect: (step: TourStep | null, index: number | null) => void;
  onPickNode: (id: string) => void;
};

export function TourPanel({ projectId, layers, activeStep, onSelect, onPickNode }: Props) {
  const [steps, setSteps] = useState<TourStep[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    setError(null);
    getJson<{ steps: TourStep[] }>(`/projects/${projectId}/tour`)
      .then((r) => setSteps(r.steps))
      .catch((e: Error) => setError(e.message));
  }, [projectId]);

  if (error) return <p className="muted pad">{error}</p>;
  if (steps.length === 0) {
    return <p className="muted pad">Index the project to generate a guided tour.</p>;
  }
  const current = activeStep !== null ? steps[activeStep] : null;

  return (
    <div className="tour">
      <div className="tour-head">
        <p className="muted">
          A suggested reading order: entry points first, then routing, handlers, data and tests.
        </p>
        <div className="tour-nav">
          <button
            type="button"
            className="btn ghost small"
            disabled={activeStep === null || activeStep === 0}
            onClick={() => onSelect(steps[(activeStep ?? 1) - 1], (activeStep ?? 1) - 1)}
          >
            ← Prev
          </button>
          <span className="muted">{activeStep === null ? "Not started" : `${activeStep + 1} / ${steps.length}`}</span>
          <button
            type="button"
            className="btn primary small"
            onClick={() => {
              const next = activeStep === null ? 0 : Math.min(activeStep + 1, steps.length - 1);
              onSelect(steps[next], next);
            }}
            disabled={activeStep === steps.length - 1}
          >
            {activeStep === null ? "Start tour" : "Next →"}
          </button>
        </div>
      </div>

      <ol className="tour-steps">
        {steps.map((s, i) => (
          <li key={s.order} className={i === activeStep ? "active" : ""}>
            <button type="button" className="tour-step-title" onClick={() => onSelect(s, i)}>
              <span className="tour-index">{s.order}</span>
              {s.title}
            </button>
            {i === activeStep ? (
              <div className="tour-step-body">
                <p>{s.description}</p>
                {s.lesson ? (
                  <p className="tour-lesson">
                    <strong>Concept · </strong>
                    {s.lesson}
                  </p>
                ) : null}
                <ul className="tour-nodes">
                  {s.nodes.map((n) => (
                    <li key={n.id}>
                      <button type="button" onClick={() => onPickNode(n.id)}>
                        <span className="legend-dot" style={{ background: layerColor(layers, n.layer) }} />
                        <span className="tour-node-name">{n.name}</span>
                        <span className="tour-node-path">{n.source_path ?? n.node_type}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </li>
        ))}
      </ol>
      {current ? (
        <button type="button" className="btn ghost small tour-exit" onClick={() => onSelect(null, null)}>
          End tour
        </button>
      ) : null}
    </div>
  );
}
