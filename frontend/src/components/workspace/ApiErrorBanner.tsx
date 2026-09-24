/**
 * Inline error for a failed request (spec §3.4 "Error", §9). The framing
 * line depends on the error kind; the backend's own `detail` is always shown
 * verbatim below it: never replaced with "Something went wrong".
 */
import type { ApiError } from "../../lib/api/errors";
import { errorGuidance, errorHeadline } from "../../lib/api/errors";
import { CopyButton } from "../common/CopyButton";
import { Icon } from "../common/Icon";
import "./banners.css";

interface ApiErrorBannerProps {
  error: ApiError;
  onRetry?: () => void;
  onDismiss?: () => void;
  onOpenSettings?: () => void;
}

export function ApiErrorBanner({ error, onRetry, onDismiss, onOpenSettings }: ApiErrorBannerProps) {
  const guidance = errorGuidance(error);
  const isBug = error.kind === "invalid_coordinates";
  return (
    <div className={`ebanner ${error.kind === "timeout" ? "is-warn" : ""}`} role="alert">
      <div className="ebanner-head">
        <Icon name={error.kind === "timeout" ? "alertTriangle" : "alertOctagon"} size={16} />
        <strong>{errorHeadline(error)}</strong>
        {error.status !== null && <span className="badge">HTTP {error.status}</span>}
        <span className="badge mono">{error.endpoint}</span>
      </div>
      {guidance && <p className="ebanner-guidance">{guidance}</p>}
      <pre className="ebanner-detail">
        <code>{error.detail}</code>
      </pre>
      <div className="ebanner-actions">
        {onRetry && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>
            <Icon name="refresh" size={14} /> Try again
          </button>
        )}
        {error.kind === "llm_config" && onOpenSettings && (
          <button type="button" className="btn btn-primary btn-sm" onClick={onOpenSettings}>
            <Icon name="key" size={14} /> Open Settings
          </button>
        )}
        {(isBug || error.kind === "server") && (
          <CopyButton
            label="Copy diagnostics"
            getText={() =>
              JSON.stringify(
                { endpoint: error.endpoint, status: error.status, kind: error.kind, detail: error.detail, at: new Date().toISOString() },
                null,
                2,
              )
            }
          />
        )}
        {onDismiss && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onDismiss}>
            Dismiss
          </button>
        )}
      </div>
    </div>
  );
}
