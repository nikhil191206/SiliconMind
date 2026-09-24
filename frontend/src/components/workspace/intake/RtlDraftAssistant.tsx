/**
 * RtlDraftAssistant: spec §3.2 (beginner path).
 *
 * Describe → /api/intake/draft-rtl → review in RtlPreview → synthesize.
 * The description, design name and draft are owned by the parent so they
 * survive errors and "Try again" (§3.4).
 *
 * No template dropdown: the backend doesn't expose a template list yet, and
 * the spec says to omit it rather than hardcode fake template names.
 */
import { useState } from "react";
import { useSession } from "../../../state/SessionProvider";
import { Icon } from "../../common/Icon";
import { DesignNameField, designNameError } from "./DesignNameField";
import { RtlPreview } from "./RtlPreview";

export interface DraftState {
  description: string;
  designName: string;
  rtl: string | null;
}

const EXAMPLES = [
  "An 8-bit counter with enable and synchronous clear",
  "A 16-entry FIFO buffer, 8 bits wide, with full and empty flags",
  "A 16-bit ALU that supports add, subtract, and, or, xor and shifts",
];

export function RtlDraftAssistant({ draft, setDraft }: { draft: DraftState; setDraft(d: DraftState): void }) {
  const { state, actions } = useSession();
  const [touched, setTouched] = useState(false);
  const busy = state.inFlight?.kind === "draft" || state.inFlight?.kind === "synthesize";

  async function onDraft() {
    if (!draft.description.trim()) return;
    const rtl = await actions.draftRtl(draft.description.trim());
    if (rtl !== null) setDraft({ ...draft, rtl });
  }

  async function onSynthesize() {
    setTouched(true);
    if (designNameError(draft.designName) || !draft.rtl) return;
    await actions.synthesize({ design_name: draft.designName.trim(), rtl_code: draft.rtl });
  }

  if (draft.rtl !== null) {
    return (
      <div className="stack" style={{ ["--stack-gap" as string]: "16px" }}>
        <DesignNameField value={draft.designName} onChange={(v) => setDraft({ ...draft, designName: v })} showError={touched} />
        <RtlPreview
          rtlCode={draft.rtl}
          onChange={(code) => setDraft({ ...draft, rtl: code })}
          onConfirm={onSynthesize}
          onDiscard={() => setDraft({ ...draft, rtl: null })}
          busy={busy}
        />
      </div>
    );
  }

  return (
    <div className="stack" style={{ ["--stack-gap" as string]: "14px" }}>
      <div className="field">
        <label className="label" htmlFor="describe">
          Describe what you want to build
        </label>
        <textarea
          id="describe"
          className="textarea"
          rows={6}
          value={draft.description}
          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
          placeholder="e.g. A small processor datapath with a 16-bit ALU, a register file, and a program counter"
          disabled={busy}
        />
        <div className="intake-examples">
          <span className="hint">Try:</span>
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              className="chip"
              onClick={() => setDraft({ ...draft, description: ex })}
              disabled={busy}
            >
              {ex}
            </button>
          ))}
        </div>
      </div>
      <div className="row">
        <button type="button" className="btn btn-primary" onClick={onDraft} disabled={busy || !draft.description.trim()}>
          <Icon name="sparkles" size={14} /> Draft RTL
        </button>
        <span className="hint">You'll review the generated Verilog before anything is synthesized.</span>
      </div>
    </div>
  );
}
