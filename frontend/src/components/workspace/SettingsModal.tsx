/**
 * Settings: spec §3.3 (ApiKeySettings) plus connection/demo controls.
 *
 * The API key:
 *   - lives only in this browser's localStorage,
 *   - is masked with a show/hide toggle,
 *   - is attached only to requests to the SiliconMind backend,
 *   - is never logged (no console output anywhere touches it).
 */
import { useEffect, useState } from "react";
import { DEMO_SCENARIOS, type DemoScenario } from "../../lib/mock/mockBackend";
import { useSession } from "../../state/SessionProvider";
import { Icon } from "../common/Icon";
import { Modal } from "../common/Modal";
import "./SettingsModal.css";

export function SettingsModal() {
  const { state, dispatch } = useSession();
  const [key, setKey] = useState(state.apiKey ?? "");
  const [reveal, setReveal] = useState(false);
  const [baseUrl, setBaseUrl] = useState(state.apiBaseUrl);

  // Re-sync drafts each time the dialog opens.
  useEffect(() => {
    if (state.settingsOpen) {
      setKey(state.apiKey ?? "");
      setBaseUrl(state.apiBaseUrl);
      setReveal(false);
    }
  }, [state.settingsOpen, state.apiKey, state.apiBaseUrl]);

  const close = () => dispatch({ type: "closeSettings" });

  function save() {
    dispatch({ type: "setApiKey", apiKey: key.trim() ? key.trim() : null });
    dispatch({ type: "setApiBaseUrl", url: baseUrl.trim() });
    close();
  }

  return (
    <Modal
      open={state.settingsOpen}
      title="Settings"
      onClose={close}
      width={560}
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={close}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary" onClick={save}>
            Save
          </button>
        </>
      }
    >
      <div className="settings">
        {state.settingsReason && (
          <p className="settings-reason" role="status">
            <Icon name="info" size={14} /> {state.settingsReason}
          </p>
        )}

        <section className="settings-section" aria-labelledby="set-key">
          <h3 id="set-key" className="settings-title">
            <Icon name="key" size={15} /> LLM API key
          </h3>
          <p className="hint">
            Bring your own key (Groq or any OpenAI-compatible provider). It's used for drafting RTL and for
            natural-language edits. It's stored only in this browser and sent only to the SiliconMind backend.
          </p>
          <div className="settings-key">
            <input
              id="api-key"
              className="input input-mono"
              type={reveal ? "text" : "password"}
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="sk-… / gsk_…"
              autoComplete="off"
              spellCheck={false}
              aria-label="API key"
            />
            <button
              type="button"
              className="btn btn-secondary btn-icon"
              onClick={() => setReveal((r) => !r)}
              aria-label={reveal ? "Hide key" : "Show key"}
              aria-pressed={reveal}
            >
              <Icon name={reveal ? "eyeOff" : "eye"} />
            </button>
            {key && (
              <button type="button" className="btn btn-ghost" onClick={() => setKey("")}>
                Clear
              </button>
            )}
          </div>
          <p className="hint">
            {state.apiKey ? (
              <>
                <Icon name="check" size={12} /> A key is saved.
              </>
            ) : (
              "No key saved yet."
            )}
            {state.demoMode && " In Demo mode no LLM is called, so a key isn't required."}
          </p>
        </section>

        <hr className="divider" />

        <section className="settings-section" aria-labelledby="set-conn">
          <h3 id="set-conn" className="settings-title">
            <Icon name="network" size={15} /> Backend connection
          </h3>
          <label className="settings-switch">
            <input
              type="checkbox"
              checked={state.demoMode}
              onChange={(e) => dispatch({ type: "setDemoMode", demoMode: e.target.checked })}
            />
            <span>
              <strong>Demo mode</strong>
              <span className="hint">
                Use an in-browser mock backend. It's on by default because backend/main.py isn't in the repo yet.
              </span>
            </span>
          </label>

          {!state.demoMode && (
            <div className="field">
              <label className="label" htmlFor="api-base">
                API base URL
              </label>
              <input
                id="api-base"
                className="input input-mono"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="(empty = same origin, proxied to http://localhost:8000 in dev)"
              />
            </div>
          )}

          {state.demoMode && (
            <div className="field">
              <label className="label" htmlFor="demo-scenario">
                Demo scenario
              </label>
              <select
                id="demo-scenario"
                className="select"
                value={state.demoScenario}
                onChange={(e) => dispatch({ type: "setDemoScenario", scenario: e.target.value as DemoScenario })}
              >
                {DEMO_SCENARIOS.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
              <span className="hint">{DEMO_SCENARIOS.find((s) => s.id === state.demoScenario)?.description}</span>
              <span className="hint">Force each error or contradiction path from the spec's §9 to see how the UI handles it.</span>
            </div>
          )}
        </section>
      </div>
    </Modal>
  );
}
