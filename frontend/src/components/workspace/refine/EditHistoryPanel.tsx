/**
 * EditHistoryPanel: spec §6.4-6.5.
 *
 * Chronological list of every state this session: instruction, diff_summary,
 * timestamp, "View this state". Undo is a VIEW operation that moves the
 * pointer to the parent state; no backend call. Editing from an earlier
 * state creates a new branch (shown with its parent), nothing is discarded.
 * History lives only in this tab (§14.5), said plainly.
 */
import { formatTime } from "../../../lib/format";
import { isVerified } from "../../../state/selectors";
import type { HistoryEntry } from "../../../state/sessionTypes";
import { Icon } from "../../common/Icon";

interface EditHistoryPanelProps {
  history: HistoryEntry[];
  currentIndex: number;
  onJumpTo(i: number): void;
}

export function EditHistoryPanel({ history, currentIndex, onJumpTo }: EditHistoryPanelProps) {
  const current = history[currentIndex];
  const parent = current?.parentIndex ?? null;

  return (
    <div className="history">
      <div className="row history-tools">
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={parent === null}
          onClick={() => parent !== null && onJumpTo(parent)}
          title="View the state this one was edited from"
        >
          <Icon name="undo" size={13} /> Undo (view previous state)
        </button>
      </div>
      <ol className="history-list" reversed>
        {[...history.keys()].reverse().map((i) => {
          const h = history[i];
          const active = i === currentIndex;
          const branched = h.parentIndex !== null && h.parentIndex !== i - 1;
          return (
            <li key={i} className={`history-item ${active ? "is-active" : ""}`} aria-current={active ? "step" : undefined}>
              <div className="history-dot" aria-hidden="true" />
              <div className="history-body">
                <div className="history-row">
                  <span className="mono history-idx">#{i}</span>
                  <span className="history-text">
                    {h.triggeringInstruction === null ? <em>Initial generation</em> : `“${h.triggeringInstruction}”`}
                  </span>
                </div>
                {h.diffSummary && <p className="history-summary">{h.diffSummary}</p>}
                <div className="history-row history-meta">
                  <span className="faint mono">{formatTime(h.timestamp)}</span>
                  <span className={`badge ${isVerified(h.verificationStatus) ? "badge-ok" : "badge-warn"}`}>
                    {isVerified(h.verificationStatus) ? "verified" : "unverified"}
                  </span>
                  <span className="faint mono">seed {h.placement.generation_metadata.seed}</span>
                  {branched && <span className="badge">branch from #{h.parentIndex}</span>}
                  <span className="spacer" />
                  {active ? (
                    <span className="history-viewing">Viewing</span>
                  ) : (
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => onJumpTo(i)}>
                      View this state
                    </button>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
      <p className="hint">
        History lives only in this browser tab. Refreshing the page clears it, because there's no server-side history
        yet.
      </p>
    </div>
  );
}
