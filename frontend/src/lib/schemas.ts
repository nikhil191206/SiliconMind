/**
 * TypeScript mirrors of the Pydantic contracts in `shared/schemas/`.
 *
 * These are hand-kept in sync with the Python source of truth: every field
 * here exists there, with the same name and meaning. If a schema changes in
 * `shared/schemas/` (see its CHANGELOG.md), change it here in the same PR.
 */

// ---- shared/schemas/circuit_graph.py ------------------------------------

export type NodeType = "MACRO" | "STD_CELL";

export interface CircuitNode {
  /** 0-indexed, contiguous. */
  node_id: number;
  type: NodeType;
  /** Die units. */
  width: number;
  /** Die units. */
  height: number;
  pin_count: number;
}

export interface CircuitHyperedge {
  /** 0-indexed, contiguous. */
  net_id: number;
  /** node_id of the driving pin's node, or null if primary input. */
  driver_node: number | null;
  sink_nodes: number[];
}

export interface Die {
  width: number;
  height: number;
}

export interface CircuitGraph {
  design_name: string;
  nodes: CircuitNode[];
  hyperedges: CircuitHyperedge[];
  die: Die;
}

// ---- shared/schemas/placement.py ----------------------------------------

export const ORIENTATIONS = ["N", "S", "E", "W", "FN", "FS", "FE", "FW"] as const;
export type Orientation = (typeof ORIENTATIONS)[number];

export interface PlacementEntry {
  node_id: number;
  /** Lower-left corner of the node's bounding box (shared/metrics/geometry.py). */
  x: number;
  y: number;
  orientation: Orientation;
}

export interface GenerationMetadata {
  model_variant: string;
  seed: number;
  is_legalized: boolean;
}

export interface PlacementJSON {
  design_name: string;
  placements: PlacementEntry[];
  generation_metadata: GenerationMetadata;
}

// ---- shared/schemas/metrics.py ------------------------------------------

export interface MetricsObject {
  hpwl: number;
  congestion_overflow: number;
  /** Must be 0 in final output. */
  legality_violations: number;
  runtime_seconds: number;
}

// ---- shared/schemas/constraint.py ---------------------------------------

export type ConstraintType =
  | "MOVE_AWAY_FROM"
  | "MOVE_TOWARD"
  | "FORBID_ADJACENT"
  | "FORBID_REGION"
  | "PREFER_REGION"
  | "UNCLEAR";

export type ReferenceType = "NODE" | "REGION" | "EDGE";

export interface RegionBoundingBox {
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
}

export interface ConstraintReference {
  type: ReferenceType;
  value: number | RegionBoundingBox;
}

export type Strength = "HARD" | "SOFT";

export interface ConstraintObject {
  constraint_id: string;
  source_request: string;
  frozen_node_ids: number[];
  affected_node_ids: number[];
  constraint_type: ConstraintType;
  reference: ConstraintReference;
  strength: Strength;
  confidence: number;
}

/** Mirrors ConstraintObject.requires_clarification() in constraint.py. */
export function constraintRequiresClarification(c: ConstraintObject): boolean {
  return c.constraint_type === "UNCLEAR" || c.confidence < 0.6;
}

// ---- shared/schemas/diff_report.py --------------------------------------

export interface MovedNode {
  node_id: number;
  delta_x: number;
  delta_y: number;
}

export interface DiffReport {
  constraint_id: string;
  moved_nodes: MovedNode[];
  /** Must be empty. Non-empty = bug in B's freeze enforcement, not a result. */
  unexpected_moves: number[];
  hpwl_delta: number;
  congestion_delta: number;
}
