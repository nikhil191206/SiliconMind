/**
 * Request/response contracts for the backend endpoints named in
 * FRONTEND_SPEC.md (§3-§6).
 *
 * NOTE: `backend/main.py` does not exist in the repo yet. Field names below
 * are taken verbatim from the spec (DraftRTLRequest, SynthesizeRTLRequest,
 * GeneratePlacementRequest, EditPlacementRequest/Response). When the real
 * FastAPI models land, reconcile this file against them first, everything
 * else in the frontend goes through these types.
 */
import type {
  CircuitGraph,
  ConstraintObject,
  DiffReport,
  MetricsObject,
  PlacementJSON,
} from "../schemas";

// ---- /api/intake/draft-rtl ----------------------------------------------

export interface DraftRTLRequest {
  description: string;
  template?: string | null;
  api_key?: string | null;
}

export interface DraftRTLResponse {
  rtl_code: string;
}

// ---- /api/intake/synthesize ---------------------------------------------

/** Exactly one of rtl_code / rtl_path / yosys_json_data is set. */
export interface SynthesizeRTLRequest {
  design_name: string;
  rtl_code?: string | null;
  rtl_path?: string | null;
  yosys_json_data?: unknown;
}

/**
 * The spec says this endpoint yields a CircuitGraph. Whether it's returned
 * bare or wrapped (`{ circuit_graph }` / `{ graph }`) isn't pinned down yet,
 * so the client normalises all three shapes (see endpoints.ts).
 */
export type SynthesizeRTLResponse = CircuitGraph;

// ---- /api/placement/generate --------------------------------------------

export interface GeneratePlacementRequest {
  graph: CircuitGraph;
  seed: number;
}

export interface GeneratePlacementResponse {
  placement: PlacementJSON;
  /** null whenever verification_status !== "verified" (per _legalize). */
  metrics: MetricsObject | null;
  /** "verified" | "unavailable: <reason>" */
  verification_status: string;
}

// ---- /api/placement/edit ------------------------------------------------

export interface EditPlacementRequest {
  instruction: string;
  graph: CircuitGraph;
  previous_placement: PlacementJSON;
  seed: number;
  api_key?: string | null;
}

export interface EditPlacementResponse {
  requires_clarification: boolean;
  clarification_message: string | null;
  constraint: ConstraintObject | null;
  new_placement: PlacementJSON | null;
  metrics_before: MetricsObject | null;
  metrics_after: MetricsObject | null;
  verification_status: string | null;
  diff_report: DiffReport | null;
  diff_summary: string | null;
}

/**
 * Per-call options. `onParsing` fires when a response body has arrived and
 * is being parsed, lets the UI say "Loading large placement (N MB)…" instead
 * of looking frozen during a multi-second JSON.parse (spec §11).
 */
export interface CallOptions {
  signal?: AbortSignal;
  onParsing?: (bytes: number) => void;
}

/** Everything the UI can call. Implemented by the HTTP client and the demo mock. */
export interface SiliconMindApi {
  readonly mode: "http" | "demo";
  draftRtl(req: DraftRTLRequest, opts?: CallOptions): Promise<DraftRTLResponse>;
  synthesize(req: SynthesizeRTLRequest, opts?: CallOptions): Promise<SynthesizeRTLResponse>;
  generate(req: GeneratePlacementRequest, opts?: CallOptions): Promise<GeneratePlacementResponse>;
  edit(req: EditPlacementRequest, opts?: CallOptions): Promise<EditPlacementResponse>;
}
