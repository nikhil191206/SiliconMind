/**
 * Review + Refine: spec §5 and §6 on ONE screen ("editing and looking are
 * one motion"). Canvas on the left; metrics, the instruction box and the diff
 * on the right; selection / macros / history / expert tabs below them.
 */
import { useCallback, useMemo, useRef, useState } from "react";
import { useSession } from "../../../state/SessionProvider";
import { currentEntry, parentEntry } from "../../../state/selectors";
import { Icon } from "../../common/Icon";
import { ApiErrorBanner } from "../ApiErrorBanner";
import { BaselineComparisonTab } from "../expert/BaselineComparisonTab";
import { ExpertInspector } from "../expert/ExpertInspector";
import { SeedControl } from "../expert/SeedControl";
import { GenerationProgress } from "../generate/GenerationProgress";
import { ClarificationPrompt } from "../refine/ClarificationPrompt";
import { DiffViewer } from "../refine/DiffViewer";
import { EditHistoryPanel } from "../refine/EditHistoryPanel";
import { EditInstructionBox } from "../refine/EditInstructionBox";
import type { RenderStats } from "./canvas/renderer";
import { CanvasToolbar } from "./CanvasToolbar";
import { MacroList } from "./MacroList";
import { MetricsPanel } from "./MetricsPanel";
import { FallbackScores } from "../../../fallback/FallbackScores"; // FALLBACK-REMOVE
import { NodeDetailPanel } from "./NodeDetailPanel";
import { PlacementCanvas, type PlacementCanvasHandle } from "./PlacementCanvas";
import "./Review.css";

type SideTab = "selection" | "macros" | "history" | "inspect" | "baselines";

export function ReviewView() {
  const { state, dispatch, actions } = useSession();
  const graph = state.circuitGraph!;
  const current = currentEntry(state)!;
  const parent = parentEntry(state);
  const canvasRef = useRef<PlacementCanvasHandle>(null);

  const [showNets, setShowNets] = useState(false);
  const [showLabels, setShowLabels] = useState(true);
  const [stats, setStats] = useState<(RenderStats & { zoom: number }) | null>(null);
  const [instruction, setInstruction] = useState("");
  const [tab, setTab] = useState<SideTab>("selection");

  const expert = state.persona === "expert";
  const editing = state.inFlight?.kind === "edit";
  const compareAvailable = !!(current.diffReport && parent);
  const showingBefore = compareAvailable && state.compareView === "before";
  const shownPlacement = showingBefore ? parent!.placement : current.placement;
  const movedIds = useMemo(
    () => new Set(current.diffReport?.moved_nodes.map((m) => m.node_id) ?? []),
    [current.diffReport],
  );

  const onSelect = useCallback(
    (ids: number[], mode: "replace" | "toggle" | "add") => dispatch({ type: "select", ids, mode }),
    [dispatch],
  );
  const focus = useCallback((id: number) => {
    dispatch({ type: "select", ids: [id], mode: "replace" });
    canvasRef.current?.focusNode(id);
  }, [dispatch]);

  // Throttle stats to avoid re-rendering the whole panel every frame.
  const lastStats = useRef(-Infinity);
  const onStats = useCallback((s: RenderStats & { zoom: number }) => {
    const now = performance.now();
    if (now - lastStats.current > 120) {
      lastStats.current = now;
      setStats(s);
    }
  }, []);

  const tabs: Array<{ id: SideTab; label: string; expertOnly?: boolean }> = [
    { id: "selection", label: state.selection.length ? `Selection (${state.selection.length})` : "Selection" },
    { id: "macros", label: "Macros" },
    { id: "history", label: `History (${state.placementHistory.length})` },
    { id: "inspect", label: "Inspect", expertOnly: true },
    { id: "baselines", label: "Baselines", expertOnly: true },
  ];
  // Expert-only surfaces are hidden entirely, not collapsed (§7).
  const visibleTabs = tabs.filter((t) => expert || !t.expertOnly);
  const activeTab = visibleTabs.some((t) => t.id === tab) ? tab : "selection";

  return (
    <div className="review">
      {/* ---- Canvas ---- */}
      <section className="review-canvas" aria-label="Placement visualizer">
        <PlacementCanvas
          ref={canvasRef}
          circuitGraph={graph}
          placement={shownPlacement}
          previousPlacement={!showingBefore && compareAvailable ? parent!.placement : null}
          diffReport={!showingBefore ? current.diffReport : null}
          showNets={showNets}
          showLabels={showLabels}
          selection={state.selection}
          onSelect={onSelect}
          onStats={onStats}
        />
        <CanvasToolbar
          onFit={() => canvasRef.current?.fit()}
          onZoom={(f) => canvasRef.current?.zoomBy(f)}
          showNets={showNets}
          onShowNets={setShowNets}
          showLabels={showLabels}
          onShowLabels={setShowLabels}
          selectionCount={state.selection.length}
          compare={{
            available: compareAvailable,
            view: state.compareView,
            onChange: (v) => dispatch({ type: "setCompareView", view: v }),
          }}
          stats={stats}
          expert={expert}
        />
        <div className="review-legend" aria-hidden="true">
          <span>
            <i className="lg-macro" /> macro
          </span>
          <span>
            <i className="lg-cell" /> std cell
          </span>
          <span>
            <i className="lg-pin" /> pin-1 / orientation
          </span>
          {current.diffReport && !showingBefore && (
            <span>
              <i className="lg-moved" /> moved
            </span>
          )}
          {expert && (
            <span className="mono">
              seed {shownPlacement.generation_metadata.seed} · {shownPlacement.generation_metadata.model_variant}
            </span>
          )}
          {showingBefore && <span className="lg-before">Showing the state before this edit</span>}
        </div>
      </section>

      {/* ---- Side panel ---- */}
      <aside className="review-side" aria-label="Metrics and refinement">
        <div className="review-side-scroll">
          <div className="review-step">
            <p className="caption">Step 3-4 · Review & refine</p>
            <span className="mono faint">
              state #{state.currentIndex} of {state.placementHistory.length - 1}
            </span>
          </div>

          <MetricsPanel metrics={current.metrics} verificationStatus={current.verificationStatus} persona={state.persona} />
          <FallbackScores placement={current.placement} persona={state.persona} /> {/* FALLBACK-REMOVE */}

          <div className="panel review-refine">
            {state.lastError && !editing && (
              <ApiErrorBanner
                error={state.lastError}
                onDismiss={() => dispatch({ type: "dismissError" })}
                onOpenSettings={() => dispatch({ type: "openSettings" })}
              />
            )}

            {editing && state.inFlight?.kind === "edit" ? (
              <GenerationProgress
                kind="edit"
                instruction={state.inFlight.instruction}
                nodeCount={graph.nodes.length}
                startedAt={state.inFlight.startedAt}
                parsingBytes={state.parsingBytes}
                onCancel={actions.cancel}
              />
            ) : (
              <EditInstructionBox
                value={instruction}
                onChange={setInstruction}
                selection={state.selection}
                onSubmit={(t) => void actions.edit(t)}
                busy={editing}
                disabledReason={null}
                persona={state.persona}
              />
            )}

            {state.abandonedRequest && !editing && (
              <p className="hint" role="status">
                <Icon name="info" size={12} /> Your last request was cancelled in the browser. The server may still be
                processing it.
              </p>
            )}

            {expert && !editing && (
              <div className="review-seed">
                <SeedControl seed={state.seed} onChange={(seed) => dispatch({ type: "setSeed", seed })} compact />
                <span className="hint review-seed-hint">for the next request</span>
                <span className="spacer" />
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => void actions.generate()}
                  title="Run /api/placement/generate again with this seed (adds a new history state)"
                >
                  <Icon name="refresh" size={13} /> Regenerate
                </button>
              </div>
            )}

            {state.clarification && (
              <ClarificationPrompt
                clarificationMessage={state.clarification.message}
                constraint={state.clarification.constraint}
                persona={state.persona}
                onDismiss={() => dispatch({ type: "clearClarification" })}
              />
            )}

            {current.triggeringInstruction !== null && (
              <DiffViewer
                diffSummary={current.diffSummary}
                diffReport={current.diffReport}
                before={current.metricsBefore}
                after={current.metrics}
                verificationStatus={current.verificationStatus}
                persona={state.persona}
                isMacro={(id) => graph.nodes[id]?.type === "MACRO"}
                onFocus={focus}
              />
            )}
          </div>

          <div className="panel review-tabs">
            <div className="review-tablist" role="tablist" aria-label="Details">
              {visibleTabs.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  id={`tab-${t.id}`}
                  aria-selected={activeTab === t.id}
                  aria-controls={`tabpanel-${t.id}`}
                  className={`review-tab ${activeTab === t.id ? "is-active" : ""}`}
                  onClick={() => setTab(t.id)}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <div className="review-tabpanel" role="tabpanel" id={`tabpanel-${activeTab}`} aria-labelledby={`tab-${activeTab}`}>
              {activeTab === "selection" && (
                <NodeDetailPanel
                  graph={graph}
                  placement={shownPlacement}
                  selection={state.selection}
                  onFocus={focus}
                  onClear={() => dispatch({ type: "clearSelection" })}
                  onDeselect={(id) => dispatch({ type: "select", ids: [id], mode: "toggle" })}
                />
              )}
              {activeTab === "macros" && (
                <MacroList
                  graph={graph}
                  placement={shownPlacement}
                  selection={state.selection}
                  movedIds={movedIds}
                  onToggle={(id) => dispatch({ type: "select", ids: [id], mode: "toggle" })}
                  onFocus={(id) => canvasRef.current?.focusNode(id)}
                />
              )}
              {activeTab === "history" && (
                <EditHistoryPanel
                  history={state.placementHistory}
                  currentIndex={state.currentIndex}
                  onJumpTo={(i) => dispatch({ type: "jumpTo", index: i })}
                />
              )}
              {activeTab === "inspect" && expert && (
                <ExpertInspector
                  circuitGraph={graph}
                  placement={current.placement}
                  constraint={current.constraint}
                  diffReport={current.diffReport}
                />
              )}
              {activeTab === "baselines" && expert && <BaselineComparisonTab metrics={current.metrics} />}
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
}
