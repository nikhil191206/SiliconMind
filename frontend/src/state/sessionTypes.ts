/**
 * Session store shape: FRONTEND_SPEC.md §12, field-for-field, plus a small
 * set of clearly separated view-only fields (selection, compare mode, …) that
 * never leave the browser.
 */
import type { ApiError } from "../lib/api/errors";
import type {
  CircuitGraph,
  ConstraintObject,
  DiffReport,
  MetricsObject,
  PlacementJSON,
} from "../lib/schemas";
import type { DemoScenario } from "../lib/mock/mockBackend";

export type Persona = "beginner" | "expert";

export type PipelineState = "idle" | "intake" | "generating" | "review" | "editing" | "error";

export interface HistoryEntry {
  placement: PlacementJSON;
  metrics: MetricsObject | null;
  verificationStatus: string;
  /** null for the initial /generate call. */
  triggeringInstruction: string | null;
  constraint: ConstraintObject | null;
  diffReport: DiffReport | null;
  diffSummary: string | null;
  timestamp: string;
  /** View-only: which history index this was edited from (branching undo, §6.5). */
  parentIndex: number | null;
  /** View-only: metrics_before from the edit response, for the delta table. */
  metricsBefore: MetricsObject | null;
}

export interface Clarification {
  instruction: string;
  message: string;
  constraint: ConstraintObject | null;
}

/** What request (if any) is in flight, labels must match the real endpoint (§3.4). */
export type InFlight =
  | { kind: "draft" }
  | { kind: "synthesize" }
  | { kind: "generate"; nodeCount: number; startedAt: number }
  | { kind: "edit"; instruction: string; startedAt: number }
  | null;

export interface SessionState {
  // ---- §12 contract ----
  persona: Persona;
  apiKey: string | null;
  designName: string | null;
  circuitGraph: CircuitGraph | null;
  placementHistory: HistoryEntry[];
  currentIndex: number;
  pipelineState: PipelineState;

  // ---- connection / demo ----
  demoMode: boolean;
  demoScenario: DemoScenario;
  apiBaseUrl: string;

  // ---- request lifecycle ----
  inFlight: InFlight;
  parsingBytes: number | null;
  lastError: ApiError | null;
  /** Set when the user cancelled a synchronous call; the server may still be computing (§4.2). */
  abandonedRequest: boolean;

  // ---- view-only ----
  seed: number;
  selection: number[];
  clarification: Clarification | null;
  /** Before/after compare on the canvas (§6.3). */
  compareView: "after" | "before";
  settingsOpen: boolean;
  settingsReason: string | null;
}
