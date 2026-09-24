/**
 * Permanent strip shown whenever Demo mode is on, so mock output can never be
 * mistaken for a real placement.
 */
import { DEMO_SCENARIOS, type DemoScenario } from "../../lib/mock/mockBackend";
import { Icon } from "../common/Icon";
import "./banners.css";

export function DemoStrip({ scenario, onOpenSettings }: { scenario: DemoScenario; onOpenSettings: () => void }) {
  const s = DEMO_SCENARIOS.find((d) => d.id === scenario);
  return (
    <div className="demo-strip" role="note">
      <Icon name="flask" size={14} />
      <p>
        <strong>Demo mode</strong>: an in-browser mock backend. Nothing here is a real placement, real synthesis, or a
        real LLM call.
        {scenario !== "verified" && s && (
          <>
            {" "}
            Forced scenario: <span className="mono">{s.label}</span>.
          </>
        )}
      </p>
      <button type="button" className="btn btn-ghost btn-sm" onClick={onOpenSettings}>
        Connection settings
      </button>
    </div>
  );
}
