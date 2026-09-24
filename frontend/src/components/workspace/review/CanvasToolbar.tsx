/**
 * Toolbar floating over the canvas: zoom/fit, nets toggle (off by default,
 * scoped to the selection: §5.3), labels, before/after compare (§6.3), and
 * live render stats (LOD mode, visible counts) so perf is observable.
 */
import type { RenderStats } from "./canvas/renderer";
import { formatCompact } from "../../../lib/format";
import { Icon } from "../../common/Icon";

interface CanvasToolbarProps {
  onFit(): void;
  onZoom(f: number): void;
  showNets: boolean;
  onShowNets(v: boolean): void;
  showLabels: boolean;
  onShowLabels(v: boolean): void;
  selectionCount: number;
  compare: { available: boolean; view: "before" | "after"; onChange(v: "before" | "after"): void };
  stats: (RenderStats & { zoom: number }) | null;
  expert: boolean;
}

export function CanvasToolbar(p: CanvasToolbarProps) {
  return (
    <>
      <div className="ctool ctool-left" role="toolbar" aria-label="Canvas view">
        <button type="button" className="ctool-btn" onClick={() => p.onZoom(1.25)} aria-label="Zoom in" title="Zoom in (+)">
          <Icon name="zoomIn" size={15} />
        </button>
        <button type="button" className="ctool-btn" onClick={() => p.onZoom(0.8)} aria-label="Zoom out" title="Zoom out (−)">
          <Icon name="zoomOut" size={15} />
        </button>
        <button type="button" className="ctool-btn" onClick={p.onFit} aria-label="Fit die" title="Fit die (0)">
          <Icon name="maximize" size={15} />
        </button>
        <span className="ctool-sep" />
        <button
          type="button"
          className={`ctool-btn ctool-text ${p.showNets ? "is-on" : ""}`}
          aria-pressed={p.showNets}
          onClick={() => p.onShowNets(!p.showNets)}
          title="Show nets touching the selected nodes"
        >
          <Icon name="network" size={14} /> Nets
          {p.showNets && p.selectionCount === 0 && <span className="ctool-note">select a node</span>}
        </button>
        <button
          type="button"
          className={`ctool-btn ctool-text ${p.showLabels ? "is-on" : ""}`}
          aria-pressed={p.showLabels}
          onClick={() => p.onShowLabels(!p.showLabels)}
        >
          Labels
        </button>
      </div>

      {p.compare.available && (
        <div className="ctool ctool-center" role="radiogroup" aria-label="Compare before and after the edit">
          {(["before", "after"] as const).map((v) => (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={p.compare.view === v}
              className={`ctool-seg ${p.compare.view === v ? "is-on" : ""}`}
              onClick={() => p.compare.onChange(v)}
            >
              {v === "before" ? "Before edit" : "After edit"}
            </button>
          ))}
        </div>
      )}

      {p.stats && (
        <div className="ctool ctool-right mono" aria-live="off">
          <span title="Level of detail for standard cells">{p.stats.mode === "density" ? "density LOD" : "all cells"}</span>
          {p.expert && (
            <>
              <span>{formatCompact(p.stats.visibleCells)} cells</span>
              <span>{p.stats.visibleMacros} macros</span>
              <span>{p.stats.ms.toFixed(1)} ms</span>
            </>
          )}
          <span>{p.stats.zoom < 10 ? p.stats.zoom.toFixed(2) : Math.round(p.stats.zoom)}×</span>
        </div>
      )}
    </>
  );
}
