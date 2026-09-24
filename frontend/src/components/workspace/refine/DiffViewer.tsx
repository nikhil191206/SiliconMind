/**
 * DiffViewer: spec §6.3.
 *
 * - diff_summary first (the plain-language line beginners read).
 * - Metrics before → after with a signed delta, colour AND +/− text (§10),
 *   only when both sides were actually verified; otherwise the two
 *   verification statuses are surfaced directly.
 * - moved_nodes as an inspectable list: one click focuses each on canvas.
 * - unexpected_moves is NOT folded in here; it triggers the red banner.
 */
import type { DiffReport, MetricsObject } from "../../../lib/schemas";
import { formatNumber, formatSigned } from "../../../lib/format";
import type { Persona } from "../../../state/sessionTypes";
import { Icon } from "../../common/Icon";

interface DiffViewerProps {
  diffSummary: string | null;
  diffReport: DiffReport | null;
  before: MetricsObject | null;
  after: MetricsObject | null;
  verificationStatus: string;
  persona: Persona;
  isMacro(id: number): boolean;
  onFocus(id: number): void;
}

const ROWS: Array<{ key: keyof MetricsObject; label: string; lowerIsBetter: boolean; digits: number }> = [
  { key: "hpwl", label: "HPWL", lowerIsBetter: true, digits: 2 },
  { key: "congestion_overflow", label: "Congestion", lowerIsBetter: true, digits: 4 },
  { key: "legality_violations", label: "Legality", lowerIsBetter: true, digits: 0 },
  { key: "runtime_seconds", label: "Runtime (s)", lowerIsBetter: true, digits: 3 },
];

export function DiffViewer({ diffSummary, diffReport, before, after, verificationStatus, persona, isMacro, onFocus }: DiffViewerProps) {
  const moved = diffReport?.moved_nodes ?? [];
  const movedMacros = moved.filter((m) => isMacro(m.node_id));
  const movedCells = moved.length - movedMacros.length;

  return (
    <section className="diff" aria-labelledby="diff-title">
      <h3 id="diff-title" className="caption">
        What changed
      </h3>
      {diffSummary && (
        <p className="diff-summary">
          <Icon name="checkCircle" size={15} /> {diffSummary}
        </p>
      )}

      {before && after ? (
        <table className="diff-table">
          <caption className="visually-hidden">Metrics before and after this edit</caption>
          <thead>
            <tr>
              <th scope="col">Metric</th>
              <th scope="col">Before</th>
              <th scope="col">After</th>
              <th scope="col">Δ</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((r) => {
              const d = (after[r.key] as number) - (before[r.key] as number);
              const better = r.lowerIsBetter ? d < 0 : d > 0;
              const cls = d === 0 ? "is-flat" : better ? "is-better" : "is-worse";
              return (
                <tr key={r.key}>
                  <th scope="row">{r.label}</th>
                  <td className="mono">{formatNumber(before[r.key] as number, r.digits)}</td>
                  <td className="mono">{formatNumber(after[r.key] as number, r.digits)}</td>
                  <td className={`mono diff-delta ${cls}`}>
                    {formatSigned(d, r.digits)}
                    <span className="visually-hidden">{d === 0 ? " (no change)" : better ? " (better)" : " (worse)"}</span>
                    {d !== 0 && r.key !== "runtime_seconds" && (
                      <Icon name={better ? "check" : "alertTriangle"} size={11} />
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <p className="hint diff-noverify">
          <Icon name="alertTriangle" size={12} /> Metric deltas need both states verified. Status:{" "}
          <span className="mono">{verificationStatus}</span>
        </p>
      )}

      {diffReport && (
        <div className="diff-moved">
          <p className="diff-moved-head">
            <strong>{movedMacros.length}</strong> macro{movedMacros.length === 1 ? "" : "s"} moved
            {movedCells > 0 && (
              <span className="faint">
                {" "}
                · {movedCells} displaced std cell{movedCells === 1 ? "" : "s"} re-placed
              </span>
            )}
          </p>
          {movedMacros.length > 0 && (
            <ul className="diff-moved-list">
              {movedMacros.slice(0, 40).map((m) => (
                <li key={m.node_id}>
                  <button type="button" className="diff-moved-btn" onClick={() => onFocus(m.node_id)}>
                    <span className="mono">M{m.node_id}</span>
                    {persona === "expert" && (
                      <span className="mono faint">
                        Δ({formatSigned(m.delta_x, 1)}, {formatSigned(m.delta_y, 1)})
                      </span>
                    )}
                    <Icon name="target" size={12} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          {persona === "expert" && (
            <p className="hint mono">
              hpwl_delta {formatSigned(diffReport.hpwl_delta)} · congestion_delta {formatSigned(diffReport.congestion_delta, 4)} ·
              unexpected_moves [{diffReport.unexpected_moves.length ? diffReport.unexpected_moves.slice(0, 8).join(", ") : ""}]
            </p>
          )}
        </div>
      )}
    </section>
  );
}
