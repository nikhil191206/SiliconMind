/**
 * TEMPORARY DEMO FALLBACK. Shows the fallback server's `fallback_report`
 * next to the (correctly empty) spec MetricsPanel.
 *
 * Kept visually separate on purpose: MetricsPanel only ever shows a
 * verified MetricsObject. These numbers are real shared/metrics output on a
 * classical placement that was never DREAMPlace-legalized or verified, and
 * the panel says so. Congestion is shown as not measured, never 0.
 */
import { formatInt, formatNumber, formatSeconds } from "../lib/format";
import type { PlacementJSON } from "../lib/schemas";
import type { Persona } from "../state/sessionTypes";
import { Icon } from "../components/common/Icon";
import { fallbackReportFor } from "./fallbackApi";
import "./fallback.css";

function pct(after: number, before: number): string {
  if (!before) return "";
  const p = ((after - before) / before) * 100;
  if (Math.abs(p) < 0.05) return "essentially unchanged";
  return `${p > 0 ? "+" : "−"}${formatNumber(Math.abs(p), 1)}%`;
}

export function FallbackScores({ placement, persona }: { placement: PlacementJSON; persona: Persona }) {
  const r = fallbackReportFor(placement);
  if (!r) return null;
  const vsBaseline = r.baseline.hpwl > 0 ? r.baseline.hpwl / Math.max(r.hpwl, 1e-9) : null;

  return (
    <section className="panel fb-scores" aria-labelledby="fb-scores-title">
      <header className="panel-head">
        <Icon name="chart" size={15} />
        <h2 id="fb-scores-title" className="fb-scores-title">
          Fallback scores
        </h2>
        <span className="spacer" />
        <span className="badge badge-warn">unverified</span>
      </header>
      <div className="panel-body">
        <dl className="fb-grid">
          <div>
            <dt>HPWL</dt>
            <dd className="mono">{formatNumber(r.hpwl, 0)}</dd>
            {persona === "beginner" && <p className="hint">Total estimated wire length. Lower is better.</p>}
            {r.before && <p className="hint mono">was {formatNumber(r.before.hpwl, 0)} · {pct(r.hpwl, r.before.hpwl)}</p>}
          </div>
          <div>
            <dt>Macro legality violations</dt>
            <dd className={`mono ${r.legality_violations > 0 ? "fb-bad" : "fb-good"}`}>{formatInt(r.legality_violations)}</dd>
            {persona === "beginner" && <p className="hint">Big blocks overlapping or hanging off the chip. Must be 0.</p>}
          </div>
          <div>
            <dt>Congestion overflow</dt>
            <dd className="fb-na">Not measured</dd>
            <p className="hint">{r.congestion_note}</p>
          </div>
          <div>
            <dt>Placer runtime</dt>
            <dd className="mono">{formatSeconds(r.runtime_seconds)}</dd>
          </div>
        </dl>
        <p className="fb-baseline">
          <span className="caption">vs. baseline</span>{" "}
          <span className="mono">{r.baseline.name}</span>: HPWL {formatNumber(r.baseline.hpwl, 0)}
          {vsBaseline !== null && (
            <>
              {" "}
              → this placement is <strong>{formatNumber(vsBaseline, 1)}×</strong> {vsBaseline >= 1 ? "shorter" : "longer"}
            </>
          )}
        </p>
        <p className="hint">
          Scored by <span className="mono">{r.scored_by}</span> on a placement from{" "}
          <span className="mono">{r.method}</span>. Not DREAMPlace-legalized, not verified.
        </p>
      </div>
    </section>
  );
}
