/**
 * GenerationProgress: spec §4.2-4.3.
 *
 * Today: an INDETERMINATE indicator (no percentage the frontend has no basis
 * for), a qualitative estimate derived from the real node count, an elapsed
 * timer (a measured fact, not an estimate), and Cancel, which honestly says
 * it only aborts the browser request.
 *
 * Future: pass `stage` when the backend gains progress events (§14.2) and the
 * 4-step stepper lights up stage-by-stage as each one actually completes -
 * never interpolated.
 */
import { useEffect, useState } from "react";
import { estimateGeneration } from "../../../lib/estimate";
import { formatBytes, formatInt } from "../../../lib/format";
import { Icon } from "../../common/Icon";

export type GenerationStage = "parsing" | "encoding" | "generating" | "legalizing" | "done";

const STAGES: Array<{ id: Exclude<GenerationStage, "done">; label: string }> = [
  { id: "parsing", label: "Parse" },
  { id: "encoding", label: "Encode" },
  { id: "generating", label: "Generate" },
  { id: "legalizing", label: "Legalize" },
];

interface GenerationProgressProps {
  nodeCount: number;
  startedAt: number;
  kind: "generate" | "edit";
  instruction?: string;
  parsingBytes: number | null;
  onCancel(): void;
  /** Real stage from the backend, when it exists. Undefined today. */
  stage?: GenerationStage;
}

function useElapsed(since: number): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(t);
  }, []);
  return Math.max(0, (now - since) / 1000);
}

export function GenerationProgress({ nodeCount, startedAt, kind, instruction, parsingBytes, onCancel, stage }: GenerationProgressProps) {
  const est = estimateGeneration(nodeCount);
  const elapsed = useElapsed(startedAt);
  const title =
    parsingBytes !== null
      ? `Loading large placement (${formatInt(nodeCount)} nodes, ${formatBytes(parsingBytes)})…`
      : kind === "generate"
        ? "Generating placement"
        : "Applying your edit";

  return (
    <div className="genprog" role="status" aria-live="polite">
      <div className="genprog-head">
        <span className="spinner" />
        <div>
          <strong>{title}</strong>
          {kind === "edit" && instruction && <p className="mono genprog-instr">“{instruction}”</p>}
        </div>
      </div>

      <div className="genprog-bar" aria-hidden="true">
        <span />
      </div>

      <p className="genprog-label">
        This can take from seconds to several minutes depending on design size. For{" "}
        <strong>{formatInt(nodeCount)} nodes</strong>, expect <strong>{est.label}</strong>.
      </p>
      <p className="hint">{est.detail}</p>

      {stage && (
        <ol className="genprog-steps">
          {STAGES.map((s) => {
            const idx = STAGES.findIndex((x) => x.id === stage);
            const i = STAGES.findIndex((x) => x.id === s.id);
            const state = stage === "done" || i < idx ? "done" : i === idx ? "active" : "todo";
            return (
              <li key={s.id} className={`is-${state}`}>
                <span>{state === "done" ? <Icon name="check" size={12} /> : i + 1}</span>
                {s.label}
              </li>
            );
          })}
        </ol>
      )}

      <div className="genprog-foot">
        <span className="mono faint">elapsed {elapsed.toFixed(0)}s</span>
        <span className="spacer" />
        <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel}>
          <Icon name="stop" size={12} /> Cancel
        </button>
      </div>
      <p className="hint">
        Cancel stops waiting in your browser. Because the backend call is synchronous, the server may keep computing.
      </p>
    </div>
  );
}
