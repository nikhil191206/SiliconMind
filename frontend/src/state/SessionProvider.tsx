/**
 * Session context: state + dispatch + the API instance + async actions.
 *
 * Components never call fetch directly; they call the actions here, which own
 * the in-flight/abort/error lifecycle so every screen reports it identically.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, type ReactNode } from "react";
import { ApiError } from "../lib/api/errors";
import { createHttpApi } from "../lib/api/httpClient";
import { isFallbackActive, withFallbackCapture } from "../fallback/fallbackApi"; // FALLBACK-REMOVE
import type { SiliconMindApi, SynthesizeRTLRequest } from "../lib/api/types";
import { createDemoApi, type DemoScenario } from "../lib/mock/mockBackend";
import type { CircuitGraph } from "../lib/schemas";
import { readStored, STORAGE_KEYS, writeStored } from "../lib/storage";
import { sessionReducer, type SessionAction } from "./sessionReducer";
import type { Persona, SessionState } from "./sessionTypes";

interface SessionContextValue {
  state: SessionState;
  dispatch: React.Dispatch<SessionAction>;
  api: SiliconMindApi;
  actions: {
    draftRtl(description: string): Promise<string | null>;
    synthesize(req: SynthesizeRTLRequest): Promise<boolean>;
    loadGraph(graph: CircuitGraph): void;
    generate(): Promise<void>;
    edit(instruction: string): Promise<void>;
    cancel(): void;
    /** True if an LLM call may proceed; otherwise opens Settings with a reason (§3.3). */
    ensureApiKey(purpose: string): boolean;
  };
}

const SessionContext = createContext<SessionContextValue | null>(null);

function initialState(): SessionState {
  const envDemo = (import.meta.env.VITE_DEMO_MODE ?? "true").toLowerCase() !== "false";
  return {
    persona: readStored<Persona>(STORAGE_KEYS.persona, "beginner"),
    apiKey: readStored<string | null>(STORAGE_KEYS.apiKey, null),
    designName: null,
    circuitGraph: null,
    placementHistory: [],
    currentIndex: -1,
    pipelineState: "idle",
    demoMode: readStored<boolean>(STORAGE_KEYS.demoMode, envDemo),
    demoScenario: readStored<DemoScenario>(STORAGE_KEYS.demoScenario, "verified"),
    apiBaseUrl: readStored<string>(STORAGE_KEYS.apiBaseUrl, import.meta.env.VITE_API_BASE_URL ?? ""),
    inFlight: null,
    parsingBytes: null,
    lastError: null,
    abandonedRequest: false,
    seed: 0,
    selection: [],
    clarification: null,
    compareView: "after",
    settingsOpen: false,
    settingsReason: null,
  };
}

function toApiError(e: unknown, endpoint: string): ApiError {
  if (e instanceof ApiError) return e;
  return new ApiError({
    kind: "server",
    status: null,
    endpoint,
    detail: e instanceof Error ? e.message : String(e),
  });
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(sessionReducer, undefined, initialState);
  const abortRef = useRef<AbortController | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  // Persist preferences (never the design data, that's session-only, §14.5).
  useEffect(() => writeStored(STORAGE_KEYS.persona, state.persona), [state.persona]);
  useEffect(() => writeStored(STORAGE_KEYS.apiKey, state.apiKey), [state.apiKey]);
  useEffect(() => writeStored(STORAGE_KEYS.demoMode, state.demoMode), [state.demoMode]);
  useEffect(() => writeStored(STORAGE_KEYS.demoScenario, state.demoScenario), [state.demoScenario]);
  useEffect(() => writeStored(STORAGE_KEYS.apiBaseUrl, state.apiBaseUrl), [state.apiBaseUrl]);

  const api = useMemo<SiliconMindApi>(
    () => (state.demoMode ? createDemoApi(() => stateRef.current.demoScenario) : withFallbackCapture(createHttpApi(state.apiBaseUrl))), // FALLBACK-REMOVE: unwrap to createHttpApi(state.apiBaseUrl)
    [state.demoMode, state.apiBaseUrl],
  );

  const begin = useCallback(() => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    return controller;
  }, []);

  /** True unless a newer request has replaced this one (user cancel clears the ref → still "current"). */
  const isCurrent = useCallback(
    (c: AbortController) => abortRef.current === c || abortRef.current === null,
    [],
  );

  const ensureApiKey = useCallback((purpose: string) => {
    const s = stateRef.current;
    if (s.demoMode) return true; // the demo mock makes no LLM calls
    if (isFallbackActive()) return true; // FALLBACK-REMOVE: fallback server makes no LLM calls
    if (s.apiKey && s.apiKey.trim()) return true;
    dispatch({
      type: "openSettings",
      reason: `${purpose} uses an LLM, so it needs your own API key. Paste it here. It's stored only in this browser.`,
    });
    return false;
  }, []);

  const actions = useMemo<SessionContextValue["actions"]>(
    () => ({
      ensureApiKey,

      async draftRtl(description) {
        if (!ensureApiKey("Drafting RTL")) return null;
        const controller = begin();
        dispatch({ type: "requestStarted", inFlight: { kind: "draft" } });
        try {
          const res = await api.draftRtl(
            { description, api_key: stateRef.current.apiKey },
            { signal: controller.signal },
          );
          dispatch({ type: "requestFinished" });
          return res.rtl_code;
        } catch (e) {
          const err = toApiError(e, "/api/intake/draft-rtl");
          if (err.kind === "aborted") {
            // Superseded by a newer request → stay silent; that request owns the state now.
            if (isCurrent(controller)) dispatch({ type: "requestCancelled" });
          } else if (isCurrent(controller)) dispatch({ type: "requestFailed", error: err });
          return null;
        }
      },

      async synthesize(req) {
        const controller = begin();
        dispatch({ type: "requestStarted", inFlight: { kind: "synthesize" } });
        try {
          const graph = await api.synthesize(req, {
            signal: controller.signal,
            onParsing: (bytes) => dispatch({ type: "parsing", bytes }),
          });
          dispatch({ type: "graphReceived", graph });
          return true;
        } catch (e) {
          const err = toApiError(e, "/api/intake/synthesize");
          if (err.kind === "aborted") {
            // Superseded by a newer request → stay silent; that request owns the state now.
            if (isCurrent(controller)) dispatch({ type: "requestCancelled" });
          } else if (isCurrent(controller)) dispatch({ type: "requestFailed", error: err });
          return false;
        }
      },

      loadGraph(graph) {
        dispatch({ type: "graphReceived", graph });
      },

      async generate() {
        const s = stateRef.current;
        if (!s.circuitGraph) return;
        const controller = begin();
        dispatch({
          type: "requestStarted",
          inFlight: { kind: "generate", nodeCount: s.circuitGraph.nodes.length, startedAt: Date.now() },
        });
        try {
          const response = await api.generate(
            { graph: s.circuitGraph, seed: s.seed },
            { signal: controller.signal, onParsing: (bytes) => dispatch({ type: "parsing", bytes }) },
          );
          dispatch({ type: "generated", response });
        } catch (e) {
          const err = toApiError(e, "/api/placement/generate");
          if (err.kind === "aborted") {
            // Superseded by a newer request → stay silent; that request owns the state now.
            if (isCurrent(controller)) dispatch({ type: "requestCancelled" });
          } else if (isCurrent(controller)) dispatch({ type: "requestFailed", error: err });
        }
      },

      async edit(instruction) {
        const s = stateRef.current;
        const current = s.placementHistory[s.currentIndex];
        if (!s.circuitGraph || !current) return;
        if (!ensureApiKey("Editing with natural language")) return;
        const controller = begin();
        dispatch({ type: "clearClarification" });
        dispatch({ type: "requestStarted", inFlight: { kind: "edit", instruction, startedAt: Date.now() } });
        try {
          const response = await api.edit(
            {
              instruction,
              graph: s.circuitGraph,
              // The state being VIEWED is the parent, branching undo (§6.5).
              previous_placement: current.placement,
              seed: s.seed,
              api_key: s.apiKey,
            },
            { signal: controller.signal, onParsing: (bytes) => dispatch({ type: "parsing", bytes }) },
          );
          dispatch({ type: "edited", instruction, response });
        } catch (e) {
          const err = toApiError(e, "/api/placement/edit");
          if (err.kind === "aborted") {
            // Superseded by a newer request → stay silent; that request owns the state now.
            if (isCurrent(controller)) dispatch({ type: "requestCancelled" });
          } else if (isCurrent(controller)) dispatch({ type: "requestFailed", error: err });
        }
      },

      cancel() {
        abortRef.current?.abort();
        abortRef.current = null;
      },
    }),
    [api, begin, ensureApiKey, isCurrent],
  );

  const value = useMemo(() => ({ state, dispatch, api, actions }), [state, api, actions]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside <SessionProvider>");
  return ctx;
}
