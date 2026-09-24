/**
 * Pure reducer for the session store. All transitions of pipelineState live
 * here, so "what screen am I on" is always derivable from one place.
 */
import type { ApiError } from "../lib/api/errors";
import type { EditPlacementResponse, GeneratePlacementResponse } from "../lib/api/types";
import type { CircuitGraph } from "../lib/schemas";
import type { DemoScenario } from "../lib/mock/mockBackend";
import type { HistoryEntry, InFlight, Persona, SessionState } from "./sessionTypes";

export type SessionAction =
  | { type: "setPersona"; persona: Persona }
  | { type: "setApiKey"; apiKey: string | null }
  | { type: "setDemoMode"; demoMode: boolean }
  | { type: "setDemoScenario"; scenario: DemoScenario }
  | { type: "setApiBaseUrl"; url: string }
  | { type: "openSettings"; reason?: string | null }
  | { type: "closeSettings" }
  | { type: "setDesignName"; name: string }
  | { type: "requestStarted"; inFlight: NonNullable<InFlight> }
  | { type: "parsing"; bytes: number }
  | { type: "requestFailed"; error: ApiError }
  | { type: "requestCancelled" }
  | { type: "requestFinished" }
  | { type: "dismissError" }
  | { type: "graphReceived"; graph: CircuitGraph }
  | { type: "generated"; response: GeneratePlacementResponse }
  | { type: "edited"; instruction: string; response: EditPlacementResponse }
  | { type: "clearClarification" }
  | { type: "jumpTo"; index: number }
  | { type: "setSeed"; seed: number }
  | { type: "select"; ids: number[]; mode: "replace" | "toggle" | "add" }
  | { type: "clearSelection" }
  | { type: "setCompareView"; view: "after" | "before" }
  | { type: "startOver" };

export function sessionReducer(state: SessionState, action: SessionAction): SessionState {
  switch (action.type) {
    case "setPersona":
      return { ...state, persona: action.persona };
    case "setApiKey":
      return { ...state, apiKey: action.apiKey };
    case "setDemoMode":
      return { ...state, demoMode: action.demoMode };
    case "setDemoScenario":
      return { ...state, demoScenario: action.scenario };
    case "setApiBaseUrl":
      return { ...state, apiBaseUrl: action.url };
    case "openSettings":
      return { ...state, settingsOpen: true, settingsReason: action.reason ?? null };
    case "closeSettings":
      return { ...state, settingsOpen: false, settingsReason: null };
    case "setDesignName":
      return { ...state, designName: action.name };

    case "requestStarted":
      return {
        ...state,
        inFlight: action.inFlight,
        parsingBytes: null,
        lastError: null,
        pipelineState:
          action.inFlight.kind === "generate"
            ? "generating"
            : action.inFlight.kind === "edit"
              ? "editing"
              : "intake",
      };
    case "parsing":
      return { ...state, parsingBytes: action.bytes };
    case "requestFailed": {
      const hasPlacement = state.placementHistory.length > 0;
      return {
        ...state,
        inFlight: null,
        parsingBytes: null,
        lastError: action.error,
        // A failed edit leaves you on the canvas; a failed generate/intake is an error state.
        pipelineState: hasPlacement ? "review" : "error",
      };
    }
    case "requestCancelled": {
      const hasPlacement = state.placementHistory.length > 0;
      return {
        ...state,
        inFlight: null,
        parsingBytes: null,
        abandonedRequest: true,
        pipelineState: hasPlacement ? "review" : "idle",
      };
    }
    case "requestFinished":
      return { ...state, inFlight: null, parsingBytes: null, abandonedRequest: false, pipelineState: "idle" };
    case "dismissError":
      return {
        ...state,
        lastError: null,
        pipelineState: state.pipelineState === "error" ? "idle" : state.pipelineState,
      };

    case "graphReceived":
      return {
        ...state,
        circuitGraph: action.graph,
        designName: action.graph.design_name,
        placementHistory: [],
        currentIndex: -1,
        selection: [],
        clarification: null,
        inFlight: null,
        parsingBytes: null,
        lastError: null,
        pipelineState: "idle",
      };

    case "generated": {
      const entry: HistoryEntry = {
        placement: action.response.placement,
        metrics: action.response.metrics,
        verificationStatus: action.response.verification_status,
        triggeringInstruction: null,
        constraint: null,
        diffReport: null,
        diffSummary: null,
        timestamp: new Date().toISOString(),
        parentIndex: null,
        metricsBefore: null,
      };
      return {
        ...state,
        placementHistory: [...state.placementHistory, entry],
        currentIndex: state.placementHistory.length,
        inFlight: null,
        parsingBytes: null,
        abandonedRequest: false,
        selection: [],
        clarification: null,
        compareView: "after",
        pipelineState: "review",
      };
    }

    case "edited": {
      const r = action.response;
      if (r.requires_clarification || !r.new_placement) {
        return {
          ...state,
          inFlight: null,
          parsingBytes: null,
          abandonedRequest: false,
          pipelineState: "review",
          clarification: {
            instruction: action.instruction,
            message: r.clarification_message ?? "The instruction needs clarification.",
            constraint: r.constraint,
          },
        };
      }
      const entry: HistoryEntry = {
        placement: r.new_placement,
        metrics: r.metrics_after,
        verificationStatus: r.verification_status ?? "unavailable: no verification_status returned",
        triggeringInstruction: action.instruction,
        constraint: r.constraint,
        diffReport: r.diff_report,
        diffSummary: r.diff_summary,
        timestamp: new Date().toISOString(),
        parentIndex: state.currentIndex,
        metricsBefore: r.metrics_before,
      };
      // Branching history (§6.5): editing from an undone state appends a new
      // branch; earlier entries stay reachable in the history list.
      return {
        ...state,
        placementHistory: [...state.placementHistory, entry],
        currentIndex: state.placementHistory.length,
        inFlight: null,
        parsingBytes: null,
        abandonedRequest: false,
        clarification: null,
        compareView: "after",
        pipelineState: "review",
      };
    }
    case "clearClarification":
      return { ...state, clarification: null };

    case "jumpTo":
      if (action.index < 0 || action.index >= state.placementHistory.length) return state;
      return { ...state, currentIndex: action.index, compareView: "after" };

    case "setSeed":
      return { ...state, seed: Math.max(0, Math.floor(action.seed)) };

    case "select": {
      if (action.mode === "replace") return { ...state, selection: action.ids };
      const set = new Set(state.selection);
      for (const id of action.ids) {
        if (action.mode === "toggle" && set.has(id)) set.delete(id);
        else set.add(id);
      }
      return { ...state, selection: [...set] };
    }
    case "clearSelection":
      return { ...state, selection: [] };
    case "setCompareView":
      return { ...state, compareView: action.view };

    case "startOver":
      return {
        ...state,
        designName: null,
        circuitGraph: null,
        placementHistory: [],
        currentIndex: -1,
        pipelineState: "idle",
        inFlight: null,
        parsingBytes: null,
        lastError: null,
        selection: [],
        clarification: null,
        compareView: "after",
      };
  }
}
