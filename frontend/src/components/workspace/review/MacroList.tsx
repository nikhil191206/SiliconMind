/**
 * MacroList: the keyboard/screen-reader equivalent of canvas selection
 * (spec §10). Filterable by node_id; each row is a real checkbox so
 * selection state is announced. "Focus" pans the canvas to that macro.
 */
import { useMemo, useState } from "react";
import type { CircuitGraph, PlacementJSON } from "../../../lib/schemas";
import { formatNumber } from "../../../lib/format";
import { Icon } from "../../common/Icon";

interface MacroListProps {
  graph: CircuitGraph;
  placement: PlacementJSON;
  selection: number[];
  movedIds: Set<number>;
  onToggle(id: number): void;
  onFocus(id: number): void;
}

const LIMIT = 300;

export function MacroList({ graph, placement, selection, movedIds, onToggle, onFocus }: MacroListProps) {
  const [q, setQ] = useState("");
  const [onlyMoved, setOnlyMoved] = useState(false);
  const selected = useMemo(() => new Set(selection), [selection]);
  const pos = useMemo(() => new Map(placement.placements.map((p) => [p.node_id, p])), [placement]);
  const macros = useMemo(() => graph.nodes.filter((n) => n.type === "MACRO"), [graph]);

  const filtered = useMemo(() => {
    const term = q.trim().replace(/^m/i, "");
    return macros.filter((m) => (!term || String(m.node_id).includes(term)) && (!onlyMoved || movedIds.has(m.node_id)));
  }, [macros, q, onlyMoved, movedIds]);

  return (
    <div className="macro-list">
      <div className="macro-list-tools">
        <label className="macro-search">
          <Icon name="search" size={13} />
          <span className="visually-hidden">Filter macros by node_id</span>
          <input
            className="input"
            placeholder={`Filter ${macros.length} macros by id…`}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            inputMode="numeric"
          />
        </label>
        {movedIds.size > 0 && (
          <label className="macro-moved-toggle">
            <input type="checkbox" checked={onlyMoved} onChange={(e) => setOnlyMoved(e.target.checked)} /> moved only
          </label>
        )}
      </div>
      {macros.length === 0 ? (
        <p className="hint">This design has no macros.</p>
      ) : (
        <ul className="macro-rows" aria-label="Macros">
          {filtered.slice(0, LIMIT).map((m) => {
            const p = pos.get(m.node_id);
            return (
              <li key={m.node_id} className={`macro-row ${selected.has(m.node_id) ? "is-selected" : ""}`}>
                <label>
                  <input type="checkbox" checked={selected.has(m.node_id)} onChange={() => onToggle(m.node_id)} />
                  <span className="mono macro-id">M{m.node_id}</span>
                  <span className="mono faint macro-meta">
                    {formatNumber(m.width)}×{formatNumber(m.height)} {p ? `@ ${formatNumber(p.x)},${formatNumber(p.y)} ${p.orientation}` : ""}
                  </span>
                  {movedIds.has(m.node_id) && <span className="badge macro-moved">moved</span>}
                </label>
                <button
                  type="button"
                  className="btn btn-ghost btn-icon btn-sm"
                  onClick={() => onFocus(m.node_id)}
                  aria-label={`Focus macro ${m.node_id} on canvas`}
                >
                  <Icon name="target" size={13} />
                </button>
              </li>
            );
          })}
          {filtered.length > LIMIT && (
            <li className="hint macro-more">Showing {LIMIT} of {filtered.length}. Refine the filter.</li>
          )}
          {filtered.length === 0 && <li className="hint macro-more">No macros match.</li>}
        </ul>
      )}
    </div>
  );
}
