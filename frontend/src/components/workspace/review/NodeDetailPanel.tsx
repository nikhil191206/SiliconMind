/**
 * Detail for the current selection (spec §5.4): node_id, type, width/height,
 * pin_count, current (x, y), orientation. Multi-select shows a compact list.
 */
import type { CircuitGraph, PlacementJSON } from "../../../lib/schemas";
import { describeOrientation } from "../../../lib/geometry/geometry";
import { formatNumber } from "../../../lib/format";
import { Icon } from "../../common/Icon";

interface NodeDetailPanelProps {
  graph: CircuitGraph;
  placement: PlacementJSON;
  selection: number[];
  onFocus(id: number): void;
  onClear(): void;
  onDeselect(id: number): void;
}

export function NodeDetailPanel({ graph, placement, selection, onFocus, onClear, onDeselect }: NodeDetailPanelProps) {
  if (selection.length === 0) {
    return (
      <p className="hint node-empty">
        Click a macro on the canvas (shift-click or shift-drag for several), or pick one from the list. Selected macros
        can be referenced in your next instruction.
      </p>
    );
  }
  const byId = new Map(placement.placements.map((p) => [p.node_id, p]));

  if (selection.length === 1) {
    const id = selection[0];
    const n = graph.nodes[id];
    const p = byId.get(id);
    return (
      <div className="node-detail">
        <div className="row">
          <strong className="mono">
            {n.type === "MACRO" ? "Macro" : "Std cell"} {id}
          </strong>
          <span className="badge">{n.type}</span>
          <span className="spacer" />
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => onFocus(id)}>
            <Icon name="target" size={13} /> Focus
          </button>
          <button type="button" className="btn btn-ghost btn-sm btn-icon" onClick={onClear} aria-label="Clear selection">
            <Icon name="x" size={13} />
          </button>
        </div>
        <dl className="node-grid">
          <dt>node_id</dt>
          <dd className="mono">{id}</dd>
          <dt>type</dt>
          <dd className="mono">{n.type}</dd>
          <dt>width × height</dt>
          <dd className="mono">
            {formatNumber(n.width)} × {formatNumber(n.height)}
          </dd>
          <dt>pin_count</dt>
          <dd className="mono">{n.pin_count}</dd>
          <dt>(x, y)</dt>
          <dd className="mono">{p ? `(${formatNumber(p.x)}, ${formatNumber(p.y)})` : "not in placement"}</dd>
          <dt>orientation</dt>
          <dd className="mono">{p ? `${p.orientation}: ${describeOrientation(p.orientation)}` : "n/a"}</dd>
        </dl>
      </div>
    );
  }

  return (
    <div className="node-detail">
      <div className="row">
        <strong>{selection.length} selected</strong>
        <span className="spacer" />
        <button type="button" className="btn btn-ghost btn-sm" onClick={onClear}>
          Clear
        </button>
      </div>
      <ul className="node-chips">
        {selection.slice(0, 60).map((id) => (
          <li key={id}>
            <button type="button" className="chip mono" onClick={() => onFocus(id)} title="Focus on canvas">
              {graph.nodes[id].type === "MACRO" ? "M" : "c"}
              {id}
            </button>
            <button type="button" className="node-chip-x" onClick={() => onDeselect(id)} aria-label={`Deselect ${id}`}>
              <Icon name="x" size={10} />
            </button>
          </li>
        ))}
        {selection.length > 60 && <li className="hint">+{selection.length - 60} more</li>}
      </ul>
    </div>
  );
}
