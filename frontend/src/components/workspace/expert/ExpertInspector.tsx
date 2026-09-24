/**
 * ExpertInspector: spec §7.1. Raw, collapsible, highlighted JSON for the
 * current CircuitGraph, PlacementJSON and (after an edit) ConstraintObject /
 * DiffReport, each with copy-to-clipboard. Also shows model_variant (read-
 * only, §7.3) and the seed that produced what's on screen (§7.2).
 */
import { useState } from "react";
import type { CircuitGraph, ConstraintObject, DiffReport, PlacementJSON } from "../../../lib/schemas";
import { CopyButton } from "../../common/CopyButton";
import { JsonTree } from "../../common/JsonTree";

interface ExpertInspectorProps {
  circuitGraph: CircuitGraph;
  placement: PlacementJSON;
  constraint: ConstraintObject | null;
  diffReport: DiffReport | null;
}

type Tab = "placement" | "graph" | "constraint" | "diff";

export function ExpertInspector({ circuitGraph, placement, constraint, diffReport }: ExpertInspectorProps) {
  const [tab, setTab] = useState<Tab>("placement");
  const tabs: Array<{ id: Tab; label: string; value: unknown; available: boolean }> = [
    { id: "placement", label: "PlacementJSON", value: placement, available: true },
    { id: "graph", label: "CircuitGraph", value: circuitGraph, available: true },
    { id: "constraint", label: "ConstraintObject", value: constraint, available: !!constraint },
    { id: "diff", label: "DiffReport", value: diffReport, available: !!diffReport },
  ];
  const current = tabs.find((t) => t.id === tab)!;

  return (
    <div className="inspector">
      <dl className="inspector-meta">
        <div>
          <dt className="caption">model_variant</dt>
          <dd className="mono">{placement.generation_metadata.model_variant}</dd>
        </div>
        <div>
          <dt className="caption">seed (this placement)</dt>
          <dd className="mono">{placement.generation_metadata.seed}</dd>
        </div>
        <div>
          <dt className="caption">is_legalized</dt>
          <dd className="mono">{String(placement.generation_metadata.is_legalized)}</dd>
        </div>
      </dl>
      <p className="hint">model_variant is read-only: the API doesn't let callers choose a variant yet.</p>

      <div className="inspector-tabs" role="tablist" aria-label="Raw objects">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={`inspector-tab mono ${tab === t.id ? "is-active" : ""}`}
            onClick={() => setTab(t.id)}
            disabled={!t.available}
            title={t.available ? undefined : "Available after an edit"}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="inspector-panel">
        {current.available ? (
          <>
            <div className="row">
              <CopyButton label={`Copy ${current.label}`} getText={() => JSON.stringify(current.value, null, 2)} />
            </div>
            <JsonTree key={current.id} value={current.value} label={current.label} />
          </>
        ) : (
          <p className="hint">Available after a natural-language edit.</p>
        )}
      </div>
    </div>
  );
}
