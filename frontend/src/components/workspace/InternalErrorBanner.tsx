/**
 * InternalErrorBanner: spec §5.5, §6.3, §9.
 *
 * For responses that are 200 OK but contradict the system's own invariants
 * (verified + legality violations; non-empty unexpected_moves). Loud, red,
 * not dismissible, with a one-click "Copy diagnostic info" that dumps the raw
 * JSON so the upstream bug can be reported.
 */
import { CopyButton } from "../common/CopyButton";
import { Icon } from "../common/Icon";
import type { InvariantViolation } from "../../state/selectors";
import "./banners.css";

export function InternalErrorBanner({ violation }: { violation: InvariantViolation }) {
  return (
    <div className="ibanner" role="alert">
      <div className="ibanner-head">
        <Icon name="alertOctagon" size={18} />
        <strong>{violation.title}</strong>
      </div>
      <p>{violation.explanation}</p>
      <div className="ibanner-actions">
        <CopyButton
          label="Copy diagnostic info"
          className="btn btn-danger btn-sm"
          getText={() =>
            JSON.stringify(
              { siliconmind_diagnostic: violation.code, captured_at: new Date().toISOString(), ...(violation.diagnostic as object) },
              null,
              2,
            )
          }
        />
        <span className="ibanner-code mono">{violation.code}</span>
      </div>
    </div>
  );
}
