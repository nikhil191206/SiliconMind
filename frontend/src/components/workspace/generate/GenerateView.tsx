/**
 * Generate step: spec §4. Shown once a CircuitGraph exists and before the
 * first placement: graph summary, (expert) seed + raw CircuitGraph, and the
 * Generate action. Beginners are moved along automatically (§3.4 "transitions
 * to Generate automatically"); experts get a chance to set the seed first.
 */
import { useEffect, useRef } from "react";
import { useSession } from "../../../state/SessionProvider";
import { CopyButton } from "../../common/CopyButton";
import { Icon } from "../../common/Icon";
import { JsonTree } from "../../common/JsonTree";
import { ApiErrorBanner } from "../ApiErrorBanner";
import { SeedControl } from "../expert/SeedControl";
import { GenerationProgress } from "./GenerationProgress";
import { GraphSummary } from "./GraphSummary";
import "./Generate.css";

export function GenerateView() {
  const { state, dispatch, actions } = useSession();
  const graph = state.circuitGraph!;
  const generating = state.inFlight?.kind === "generate";
  const autoStarted = useRef<string | null>(null);

  useEffect(() => {
    if (state.persona !== "beginner") return;
    if (autoStarted.current === graph.design_name) return;
    if (state.inFlight || state.lastError || state.abandonedRequest) return;
    autoStarted.current = graph.design_name;
    void actions.generate();
  }, [graph, state.persona, state.inFlight, state.lastError, state.abandonedRequest, actions]);

  return (
    <div className="generate">
      <div className="generate-head">
        <p className="caption">Step 2 of 4 · Generate</p>
        <h1 className="h3">
          <span className="mono generate-name">{graph.design_name}</span> is ready to place
        </h1>
      </div>

      <div className="card generate-card">
        <GraphSummary graph={graph} persona={state.persona} />

        {state.lastError && (
          <ApiErrorBanner
            error={state.lastError}
            onRetry={() => {
              dispatch({ type: "dismissError" });
              void actions.generate();
            }}
            onDismiss={() => dispatch({ type: "dismissError" })}
          />
        )}

        {generating && state.inFlight?.kind === "generate" ? (
          <GenerationProgress
            kind="generate"
            nodeCount={state.inFlight.nodeCount}
            startedAt={state.inFlight.startedAt}
            parsingBytes={state.parsingBytes}
            onCancel={actions.cancel}
          />
        ) : (
          <div className="generate-actions">
            {state.persona === "expert" && (
              <SeedControl seed={state.seed} onChange={(seed) => dispatch({ type: "setSeed", seed })} />
            )}
            <button type="button" className="btn btn-primary btn-lg" onClick={() => void actions.generate()}>
              <Icon name="sparkles" size={16} /> Generate placement
            </button>
            {state.abandonedRequest && (
              <p className="hint" role="status">
                <Icon name="info" size={12} /> A previous request was cancelled in the browser; it may still be running
                on the server.
              </p>
            )}
          </div>
        )}
      </div>

      {state.persona === "expert" && (
        <details className="generate-raw">
          <summary>
            <Icon name="code" size={14} /> Raw CircuitGraph JSON
          </summary>
          <div className="generate-raw-body">
            <div className="row">
              <CopyButton label="Copy CircuitGraph" getText={() => JSON.stringify(graph, null, 2)} />
            </div>
            <JsonTree value={graph} label="CircuitGraph JSON" />
          </div>
        </details>
      )}
    </div>
  );
}
