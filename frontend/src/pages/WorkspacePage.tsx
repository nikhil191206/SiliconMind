/**
 * /app: the SiliconMind workspace (FRONTEND_SPEC.md §8).
 *
 *   header           wordmark · design_name · persona · settings   (always)
 *   demo strip       whenever Demo mode is on                      (always)
 *   banners          internal-inconsistency + verification, ABOVE the
 *                    workspace so they can never be scrolled out of view
 *   workspace        Intake  →  Generate  →  Review+Refine, chosen from
 *                    session state (mutually exclusive views of one session)
 */
import { useEffect } from "react";
import { DemoStrip } from "../components/workspace/DemoStrip";
import { GenerateView } from "../components/workspace/generate/GenerateView";
import { InternalErrorBanner } from "../components/workspace/InternalErrorBanner";
import { IntakeView } from "../components/workspace/intake/IntakeView";
import { ReviewView } from "../components/workspace/review/ReviewView";
import { SettingsModal } from "../components/workspace/SettingsModal";
import { VerificationBanner } from "../components/workspace/VerificationBanner";
import { WorkspaceHeader } from "../components/workspace/WorkspaceHeader";
import { FallbackBanner } from "../fallback/FallbackBanner"; // FALLBACK-REMOVE
import { currentEntry, invariantViolations } from "../state/selectors";
import { SessionProvider, useSession } from "../state/SessionProvider";
import { useDemoUrlHooks } from "../state/useDemoUrlHooks";
import { PRESENTATION_MODE } from "../lib/presentation";
import "./WorkspacePage.css";

function WorkspaceShell() {
  const { state, dispatch } = useSession();
  const entry = currentEntry(state);
  const violations = invariantViolations(state);
  useDemoUrlHooks();

  useEffect(() => {
    document.title = state.designName ? `${state.designName} · SiliconMind` : "Workspace · SiliconMind";
  }, [state.designName]);

  let view: JSX.Element;
  if (!state.circuitGraph) view = <IntakeView />;
  else if (!entry) view = <GenerateView />;
  else view = <ReviewView />;

  return (
    <div className="workspace">
      <WorkspaceHeader />
      <div className="workspace-banners">
        {state.demoMode && !PRESENTATION_MODE && (
          <DemoStrip scenario={state.demoScenario} onOpenSettings={() => dispatch({ type: "openSettings" })} />
        )}
        {!state.demoMode && !PRESENTATION_MODE && <FallbackBanner /> /* FALLBACK-REMOVE */}
        {violations.map((v) => (
          <InternalErrorBanner key={v.code} violation={v} />
        ))}
        {entry && (
          <VerificationBanner
            verificationStatus={entry.verificationStatus}
            persona={state.persona}
            isLegalized={entry.placement.generation_metadata.is_legalized}
            contradicted={violations.length > 0}
          />
        )}
      </div>
      <main className={`workspace-main ${entry ? "is-review" : ""}`} id="main">
        {view}
      </main>
      <SettingsModal />
    </div>
  );
}

export default function WorkspacePage() {
  return (
    <SessionProvider>
      <WorkspaceShell />
    </SessionProvider>
  );
}
