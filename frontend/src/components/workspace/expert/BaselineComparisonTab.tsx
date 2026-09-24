/**
 * BaselineComparisonTab: spec §7.4 / §14.4.
 *
 * TECHNICAL.md §1.9 requires every result to be reported against DREAMPlace
 * and the RL baseline. No live endpoint serves those results yet, so the tab
 * says so plainly instead of being omitted, and shows the table it WILL
 * fill, with this placement's own metrics in the SiliconMind column when
 * they exist.
 */
import type { MetricsObject } from "../../../lib/schemas";
import { formatNumber, formatSeconds } from "../../../lib/format";
import { Icon } from "../../common/Icon";

export function BaselineComparisonTab({ metrics }: { metrics: MetricsObject | null }) {
  const cell = (v: string | null) => (v === null ? <span className="faint mono">n/a</span> : <span className="mono">{v}</span>);
  const rows: Array<[string, string | null]> = [
    ["HPWL", metrics ? formatNumber(metrics.hpwl) : null],
    ["Congestion", metrics ? formatNumber(metrics.congestion_overflow, 4) : null],
    ["Legality", metrics ? String(metrics.legality_violations) : null],
    ["Runtime", metrics ? formatSeconds(metrics.runtime_seconds) : null],
  ];
  return (
    <div className="baseline">
      <div className="baseline-gap" role="note">
        <Icon name="info" size={15} />
        <p>
          <strong>Baseline comparison requires backend support that isn't available yet.</strong> DREAMPlace and
          RL-baseline results currently come from evaluation scripts (<span className="mono">modules/evaluation/baselines.py</span>,{" "}
          <span className="mono">experiments/</span>), not from a queryable API.
        </p>
      </div>
      <table className="baseline-table">
        <caption className="visually-hidden">This placement versus baselines</caption>
        <thead>
          <tr>
            <th scope="col">Metric</th>
            <th scope="col">This placement</th>
            <th scope="col">DREAMPlace</th>
            <th scope="col">RL baseline</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, v]) => (
            <tr key={label}>
              <th scope="row">{label}</th>
              <td>{cell(v)}</td>
              <td>
                <span className="faint mono">no endpoint</span>
              </td>
              <td>
                <span className="faint mono">no endpoint</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
