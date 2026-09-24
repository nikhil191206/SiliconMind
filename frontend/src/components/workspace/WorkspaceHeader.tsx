/**
 * Global workspace header (spec §8): wordmark, current design_name, the
 * Beginner/Expert toggle, Settings (API key), and "Start over".
 */
import { Link } from "react-router-dom";
import { useSession } from "../../state/SessionProvider";
import { Icon } from "../common/Icon";
import { Logo } from "../common/Logo";
import { PersonaToggle } from "./PersonaToggle";
import "./WorkspaceHeader.css";
import { PRESENTATION_MODE } from "../../lib/presentation";

export function WorkspaceHeader() {
  const { state, dispatch, actions } = useSession();
  const hasDesign = !!state.circuitGraph;

  function startOver() {
    if (state.placementHistory.length > 0) {
      const ok = window.confirm(
        "Start over with a new design? This session's placement history lives only in this browser tab and will be cleared.",
      );
      if (!ok) return;
    }
    actions.cancel();
    dispatch({ type: "startOver" });
  }

  return (
    <header className="ws-header">
      <Link to="/" className="ws-logo" aria-label="SiliconMind home">
        <Logo />
      </Link>

      <div className="ws-design" aria-live="polite">
        {state.designName ? (
          <>
            <span className="ws-design-sep" aria-hidden="true">
              /
            </span>
            <Icon name="cpu" size={14} />
            <span className="ws-design-name mono" title="design_name">
              {state.designName}
            </span>
          </>
        ) : null}
      </div>

      <div className="ws-header-actions">
        {!PRESENTATION_MODE && (
          <span className={`badge ${state.demoMode ? "badge-demo" : ""}`} title="Connection">
            <span className={`ws-conn-dot ${state.demoMode ? "is-demo" : ""}`} aria-hidden="true" />
            {state.demoMode ? "Demo backend" : "Live backend"}
          </span>
        )}
        <PersonaToggle persona={state.persona} onChange={(p) => dispatch({ type: "setPersona", persona: p })} />
        {hasDesign && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={startOver}>
            <Icon name="plus" size={14} /> <span className="ws-hide-sm">New design</span>
          </button>
        )}
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => dispatch({ type: "openSettings" })}
          aria-label="Settings"
        >
          <Icon name="settings" size={14} />
          <span className="ws-hide-sm">Settings</span>
          {!state.apiKey && !state.demoMode && <span className="ws-key-dot" title="No API key set" />}
        </button>
      </div>
    </header>
  );
}
