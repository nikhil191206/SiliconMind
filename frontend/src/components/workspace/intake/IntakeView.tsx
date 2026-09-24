/**
 * Intake screen: spec §3 and the §9 empty state: not a blank page but a
 * clear call to action that distinguishes the two entry paths. Persona picks
 * the default path; both are always one click away.
 */
import { useEffect, useState } from "react";
import { DEMO_SAMPLES } from "../../../lib/mock/mockGraphs";
import { formatInt } from "../../../lib/format";
import { useSession } from "../../../state/SessionProvider";
import { Icon } from "../../common/Icon";
import { ApiErrorBanner } from "../ApiErrorBanner";
import { IntakeStatus } from "./IntakeStatus";
import { PRESENTATION_MODE } from "../../../lib/presentation";
import { FallbackSamples } from "../../../fallback/FallbackSamples"; // FALLBACK-REMOVE
import { NetlistUploader, type UploadState } from "./NetlistUploader";
import { RtlDraftAssistant, type DraftState } from "./RtlDraftAssistant";
import "./Intake.css";

type Path = "describe" | "upload";

export function IntakeView() {
  const { state, dispatch, actions } = useSession();
  const [path, setPath] = useState<Path>(state.persona === "expert" ? "upload" : "describe");
  const [draft, setDraft] = useState<DraftState>({ description: "", designName: "", rtl: null });
  const [upload, setUpload] = useState<UploadState>({ file: null, check: null, designName: "" });
  const [sampleBusy, setSampleBusy] = useState<string | null>(null);

  // Persona switch nudges the default path only if the user hasn't started anything.
  useEffect(() => {
    if (!draft.description && !upload.file) setPath(state.persona === "expert" ? "upload" : "describe");
  }, [state.persona]);

  function loadSample(id: string) {
    const s = DEMO_SAMPLES.find((x) => x.id === id);
    if (!s) return;
    setSampleBusy(id);
    // Yield so the button can show its busy state before a large build.
    window.setTimeout(() => {
      actions.loadGraph(s.build());
      setSampleBusy(null);
    }, 30);
  }

  const busy = state.inFlight?.kind === "draft" || state.inFlight?.kind === "synthesize";

  return (
    <div className="intake">
      <div className="intake-hero">
        <p className="caption">Step 1 of 4 · Intake</p>
        <h1 className="h3">Get a netlist into SiliconMind</h1>
        <p className="lead">
          {state.persona === "beginner"
            ? "Start from an idea in plain English, and we'll draft the hardware description for you. Or upload a netlist if you already have one."
            : "Upload a post-synthesis structural Verilog netlist or a Yosys JSON. Or draft RTL from a description."}
        </p>
      </div>

      <div className="intake-paths" role="tablist" aria-label="Intake path">
        <button
          type="button"
          role="tab"
          aria-selected={path === "describe"}
          aria-controls="intake-panel"
          className={`intake-path ${path === "describe" ? "is-active" : ""}`}
          onClick={() => setPath("describe")}
          disabled={busy}
        >
          <span className="intake-path-icon">
            <Icon name="message" size={18} />
          </span>
          <span>
            <strong>Describe a design</strong>
            <span className="hint">No RTL yet? An LLM drafts it, you review it.</span>
          </span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={path === "upload"}
          aria-controls="intake-panel"
          className={`intake-path ${path === "upload" ? "is-active" : ""}`}
          onClick={() => setPath("upload")}
          disabled={busy}
        >
          <span className="intake-path-icon">
            <Icon name="upload" size={18} />
          </span>
          <span>
            <strong>Upload a netlist</strong>
            <span className="hint">Structural Verilog (.v) or Yosys JSON.</span>
          </span>
        </button>
      </div>

      <div id="intake-panel" role="tabpanel" className={`intake-panel card ${busy ? "is-busy" : ""}`} aria-busy={busy}>
        {state.lastError && (
          <ApiErrorBanner
            error={state.lastError}
            onRetry={() => dispatch({ type: "dismissError" })}
            onOpenSettings={() => dispatch({ type: "openSettings" })}
          />
        )}
        {state.abandonedRequest && !busy && (
          <p className="hint intake-abandoned" role="status">
            <Icon name="info" size={12} /> The previous request was cancelled in the browser. The server may still be
            processing it.
          </p>
        )}
        <IntakeStatus inFlight={state.inFlight} parsingBytes={state.parsingBytes} onCancel={actions.cancel} />
        <fieldset disabled={busy} className="intake-fieldset">
          <legend className="visually-hidden">{path === "describe" ? "Describe a design" : "Upload a netlist"}</legend>
          {path === "describe" ? (
            <RtlDraftAssistant draft={draft} setDraft={setDraft} />
          ) : (
            <NetlistUploader upload={upload} setUpload={setUpload} />
          )}
        </fieldset>
      </div>

      {!state.demoMode && <FallbackSamples disabled={busy} /> /* FALLBACK-REMOVE */}

      {state.demoMode && (
        <section className="intake-samples" aria-labelledby="samples-title">
          <div className="row">
            <h2 id="samples-title" className="caption">
              {PRESENTATION_MODE ? "Sample designs" : "Demo samples"}
            </h2>
            {!PRESENTATION_MODE && <span className="badge badge-demo">synthetic</span>}
          </div>
          <div className="intake-sample-grid">
            {DEMO_SAMPLES.map((s) => (
              <button
                key={s.id}
                type="button"
                className="intake-sample"
                onClick={() => loadSample(s.id)}
                disabled={busy || sampleBusy !== null}
              >
                <span className="mono">{s.label}</span>
                <span className="hint">{s.description}</span>
                {sampleBusy === s.id && <span className="spinner intake-sample-spin" />}
              </button>
            ))}
          </div>
          <p className="hint">
            Samples skip intake and load a CircuitGraph directly. <span className="mono">mock_toy_design</span> matches{" "}
            <span className="mono">shared/mocks</span> exactly; the others are synthetic and only for exercising the UI at
            scale ({formatInt(120_000)} nodes max).
          </p>
        </section>
      )}
    </div>
  );
}
