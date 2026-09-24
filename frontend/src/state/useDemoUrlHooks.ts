/**
 * Demo-only URL hooks for quick demos, screenshots and manual QA:
 *
 *   /app?sample=small              load a demo sample (toy | small | ibm01 | stress)
 *   /app?persona=expert            start in a persona
 *   /app?backend=live              switch off Demo mode (live backend); backend=demo switches it on
 *   /app?scenario=unverified       force a demo scenario (see DEMO_SCENARIOS)
 *   /app?sample=small&edit=move%20macro%203%20toward%20the%20left%20edge
 *                                  …then run one NL edit after the first placement
 *
 * Sample/scenario/edit are ignored unless Demo mode is on, so they can never touch a real backend.
 */
import { useEffect, useRef } from "react";
import { DEMO_SCENARIOS } from "../lib/mock/mockBackend";
import { DEMO_SAMPLES } from "../lib/mock/mockGraphs";
import { useSession } from "./SessionProvider";
import type { Persona } from "./sessionTypes";

export function useDemoUrlHooks(): void {
  const { state, dispatch, actions } = useSession();
  const params = useRef(new URLSearchParams(window.location.search));
  const done = useRef({ sample: false, edit: false });
  // ?backend=live flips Demo mode off in the first effect, but this render still sees demoMode = true.
  const forcedLive = params.current.get("backend") === "live";

  useEffect(() => {
    const p = params.current;
    const backend = p.get("backend");
    if (backend === "live" || backend === "demo") dispatch({ type: "setDemoMode", demoMode: backend === "demo" });
    const persona = p.get("persona");
    if (persona === "beginner" || persona === "expert") dispatch({ type: "setPersona", persona: persona as Persona });
    const scenario = DEMO_SCENARIOS.find((d) => d.id === p.get("scenario"));
    if (scenario) dispatch({ type: "setDemoScenario", scenario: scenario.id });
  }, [dispatch]);

  useEffect(() => {
    if (!state.demoMode || forcedLive || done.current.sample) return;
    const id = params.current.get("sample");
    const sample = DEMO_SAMPLES.find((s) => s.id === id);
    if (!sample) return;
    done.current.sample = true;
    actions.loadGraph(sample.build());
    // Experts don't auto-generate; the hook does it so the link lands on the canvas.
    window.setTimeout(() => void actions.generate(), 0);
  }, [state.demoMode, actions]);

  useEffect(() => {
    const edit = params.current.get("edit");
    if (!state.demoMode || forcedLive || !edit || done.current.edit) return;
    if (state.placementHistory.length === 1 && !state.inFlight) {
      done.current.edit = true;
      void actions.edit(edit);
    }
  }, [state.demoMode, state.placementHistory.length, state.inFlight, actions]);
}
