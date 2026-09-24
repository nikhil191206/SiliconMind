/**
 * TEMPORARY DEMO FALLBACK. Permanent strip (like DemoStrip) whenever the live
 * backend is the fallback server, so a classical placement can never be
 * mistaken for the trained model's output. Expands to list exactly what is
 * real, what is substituted, and what is not run.
 */
import { useState } from "react";
import { Icon } from "../components/common/Icon";
import { useFallbackStatus } from "./useFallbackStatus";
import "./fallback.css";

export function FallbackBanner() {
  const status = useFallbackStatus();
  const [open, setOpen] = useState(false);
  if (!status) return null;

  return (
    <div className="fb-strip" role="note">
      <div className="fb-strip-row">
        <Icon name="shield" size={14} />
        <p>
          <strong>Fallback mode</strong>: models not trained yet. A classical placer stands in for the flow-matching
          generator. All scores come from the team's real <span className="mono">shared/metrics</span> code.
        </p>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? "Hide details" : "What's real?"}
        </button>
      </div>
      {open && (
        <div className="fb-details">
          <div>
            <p className="caption">Real code running</p>
            <ul>
              {status.real.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </div>
          <div>
            <p className="caption">Substituted for today</p>
            <ul>
              {status.substituted.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </div>
          <div>
            <p className="caption">Not run</p>
            <ul>
              {status.not_run.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
