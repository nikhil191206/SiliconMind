/**
 * MetricsPanel: spec §5.5.
 *
 * - Values come straight from MetricsObject; nothing is computed here.
 * - metrics === null → "Not available: placement unverified", never 0/blank.
 * - verified + legality_violations > 0 → NOT rendered as normal metrics; the
 *   panel shows an internal-inconsistency state (the banner above carries
 *   the copyable diagnostics).
 * - Beginner persona gets a plain-English gloss under every label.
 */
import type { MetricsObject } from "../../../lib/schemas";
import { formatNumber, formatSeconds } from "../../../lib/format";
import { isVerified } from "../../../state/selectors";
import type { Persona } from "../../../state/sessionTypes";
import { Icon } from "../../common/Icon";
import { Gloss } from "../Gloss";
import "./MetricsPanel.css";

interface MetricsPanelProps {
  metrics: MetricsObject | null;
  verificationStatus: string;
  persona: Persona;
}

export function MetricsPanel({ metrics, verificationStatus, persona }: MetricsPanelProps) {
  const verified = isVerified(verificationStatus);
  const contradiction = verified && !!metrics && metrics.legality_violations > 0;

  return (
    <section className="metrics panel" aria-labelledby="metrics-title">
      <header className="panel-head">
        <Icon name="chart" size={15} />
        <h2 id="metrics-title" className="metrics-title">
          Metrics
        </h2>
        <span className="spacer" />
        {verified && !contradiction ? (
          <span className="badge badge-ok">
            <Icon name="check" size={11} /> verified
          </span>
        ) : contradiction ? (
          <span className="badge badge-danger">
            <Icon name="alertOctagon" size={11} /> inconsistent
          </span>
        ) : (
          <span className="badge badge-warn">
            <Icon name="alertTriangle" size={11} /> unverified
          </span>
        )}
      </header>

      {contradiction ? (
        <div className="metrics-contradiction" role="alert">
          <Icon name="alertOctagon" size={18} />
          <div>
            <strong>Internal inconsistency detected</strong>
            <p>
              The backend reported this placement as verified with {metrics!.legality_violations} legality violation
              {metrics!.legality_violations === 1 ? "" : "s"}. That's an upstream bug, not a result, so the metrics aren't
              shown as if they were normal. Use “Copy diagnostic info” in the red banner above to report it.
            </p>
          </div>
        </div>
      ) : metrics === null ? (
        <div className="metrics-na">
          <p>
            <strong>Not available: placement unverified</strong>
          </p>
          <p className="hint">
            Metrics are only computed after DREAMPlace/OpenROAD legalization. They're not shown as 0, because that would
            read as “no congestion”.
          </p>
        </div>
      ) : (
        <dl className="metrics-list">
          <div>
            <dt>
              Total Wirelength (HPWL)
              <Gloss persona={persona} term="hpwl" />
            </dt>
            <dd className="mono">{formatNumber(metrics.hpwl)}</dd>
          </div>
          <div>
            <dt>
              Routing Congestion
              <Gloss persona={persona} term="congestion" />
            </dt>
            <dd className="mono">{formatNumber(metrics.congestion_overflow, 4)}</dd>
          </div>
          <div>
            <dt>
              Legality Violations
              <Gloss persona={persona} term="legality" />
            </dt>
            <dd className="mono metrics-ok">
              {metrics.legality_violations}
              {metrics.legality_violations === 0 && <Icon name="check" size={13} label="zero, as required" />}
            </dd>
          </div>
          <div>
            <dt>Generation Time</dt>
            <dd className="mono">{formatSeconds(metrics.runtime_seconds)}</dd>
          </div>
        </dl>
      )}
    </section>
  );
}
