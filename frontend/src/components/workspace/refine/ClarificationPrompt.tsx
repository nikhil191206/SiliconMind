/**
 * ClarificationPrompt: spec §6.2. A first-class state, not an error.
 * Shows the backend's clarification_message verbatim. Experts additionally
 * see WHY (constraint_type, confidence, the raw ConstraintObject).
 */
import type { ConstraintObject } from "../../../lib/schemas";
import type { Persona } from "../../../state/sessionTypes";
import { Icon } from "../../common/Icon";
import { JsonTree } from "../../common/JsonTree";

interface ClarificationPromptProps {
  clarificationMessage: string;
  constraint: ConstraintObject | null;
  persona: Persona;
  onDismiss(): void;
}

export function ClarificationPrompt({ clarificationMessage, constraint, persona, onDismiss }: ClarificationPromptProps) {
  return (
    <div className="clarify" role="status" aria-live="polite">
      <div className="clarify-head">
        <Icon name="help" size={16} />
        <strong>Needs a bit more detail</strong>
        <span className="spacer" />
        <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={onDismiss} aria-label="Dismiss">
          <Icon name="x" size={13} />
        </button>
      </div>
      <p className="clarify-msg">{clarificationMessage}</p>
      <p className="hint">Your instruction is still in the box. Amend it and send again. Nothing was changed.</p>
      {persona === "expert" && constraint && (
        <details className="clarify-why">
          <summary>
            Why: <span className="mono">{constraint.constraint_type}</span> · confidence{" "}
            <span className="mono">{constraint.confidence.toFixed(2)}</span>
            <span className="faint"> (threshold 0.60)</span>
          </summary>
          <JsonTree value={constraint} label="ConstraintObject" />
        </details>
      )}
    </div>
  );
}
