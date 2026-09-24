/**
 * IntakeStatus: spec §3.4 "Submitting": the label names the endpoint that's
 * actually in flight ("Drafting RTL…" vs "Synthesizing…"), never a generic
 * "Loading".
 */
import type { InFlight } from "../../../state/sessionTypes";
import { formatBytes } from "../../../lib/format";

export function IntakeStatus({ inFlight, parsingBytes, onCancel }: { inFlight: InFlight; parsingBytes: number | null; onCancel(): void }) {
  if (!inFlight || (inFlight.kind !== "draft" && inFlight.kind !== "synthesize")) return null;
  const label =
    parsingBytes !== null
      ? `Reading response (${formatBytes(parsingBytes)})…`
      : inFlight.kind === "draft"
        ? "Drafting RTL…"
        : "Synthesizing…";
  const detail =
    inFlight.kind === "draft"
      ? "POST /api/intake/draft-rtl: an LLM is writing Verilog from your description."
      : "POST /api/intake/synthesize: Yosys is turning the design into a netlist graph.";
  return (
    <div className="intake-status" role="status" aria-live="polite">
      <span className="spinner" />
      <div>
        <strong>{label}</strong>
        <p className="hint mono">{detail}</p>
      </div>
      <button type="button" className="btn btn-ghost btn-sm" onClick={onCancel}>
        Cancel
      </button>
    </div>
  );
}
