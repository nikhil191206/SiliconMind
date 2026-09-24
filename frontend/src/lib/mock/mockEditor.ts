/**
 * DEMO MODE ONLY: rule-based stand-in for Person D's LLM constraint parser
 * + Person B's freeze-aware regeneration, so the NL edit loop (spec §6) can be
 * exercised end-to-end without a backend.
 *
 * Honours the same contract as the real system:
 *   - UNCLEAR or confidence < 0.6 → requires_clarification, generator NOT run.
 *   - Only affected_node_ids (plus std cells displaced by a moved macro) move;
 *     frozen nodes are bit-identical, so unexpected_moves is empty.
 */
import type {
  CircuitGraph,
  ConstraintObject,
  ConstraintType,
  DiffReport,
  PlacementEntry,
  PlacementJSON,
  RegionBoundingBox,
} from "../schemas";
import { effectiveDims } from "../geometry/geometry";
import { relocateCoveredCells } from "./mockPlacer";
import { uuidLike } from "../random";

type Direction = "left" | "right" | "up" | "down" | "center";

interface ParsedInstruction {
  constraint: ConstraintObject;
  direction: Direction | null;
  referenceNode: number | null;
}

const VAGUE = /\b(better|improve|optimi[sz]e|nicer|fix( it)?|good|clean ?up|whatever)\b/i;

function extractNodeIds(text: string, graph: CircuitGraph): number[] {
  const ids = new Set<number>();
  // "macro 3", "macros 3, 5 and 7", "node 12", "m3", "#4"
  const listRe = /\b(?:macros?|nodes?|blocks?|cells?)\s+((?:#?\d+\s*(?:,|and|&)?\s*)+)/gi;
  let m: RegExpExecArray | null;
  while ((m = listRe.exec(text))) {
    for (const d of m[1].match(/\d+/g) ?? []) ids.add(Number(d));
  }
  for (const d of text.match(/\b[mM](\d+)\b|#(\d+)/g) ?? []) ids.add(Number(d.replace(/\D/g, "")));
  return [...ids].filter((id) => id >= 0 && id < graph.nodes.length);
}

function extractDirection(text: string): Direction | null {
  const t = text.toLowerCase();
  if (/\b(left|west)\b/.test(t)) return "left";
  if (/\b(right|east)\b/.test(t)) return "right";
  if (/\b(top|up|upper|north)\b/.test(t)) return "up";
  if (/\b(bottom|down|lower|south)\b/.test(t)) return "down";
  if (/\b(cent(er|re)|middle)\b/.test(t)) return "center";
  return null;
}

export function parseInstruction(instruction: string, graph: CircuitGraph): ParsedInstruction {
  const text = instruction.trim();
  const ids = extractNodeIds(text, graph);
  const direction = extractDirection(text);
  const lower = text.toLowerCase();

  let type: ConstraintType = "UNCLEAR";
  let confidence = 0.2;
  let referenceNode: number | null = null;
  let affected: number[] = [];

  const awayMatch = /away from\s+(?:macro|node|block)?\s*#?m?(\d+)/i.exec(text);
  const towardMatch = /(?:toward|towards|closer to|near)\s+(?:macro|node|block)?\s*#?m?(\d+)/i.exec(text);

  if (VAGUE.test(text) && ids.length === 0) {
    type = "UNCLEAR";
    confidence = 0.2;
  } else if (awayMatch || towardMatch) {
    referenceNode = Number((awayMatch ?? towardMatch)![1]);
    affected = ids.filter((id) => id !== referenceNode);
    type = awayMatch ? "MOVE_AWAY_FROM" : "MOVE_TOWARD";
    confidence = affected.length > 0 && referenceNode < graph.nodes.length ? 0.9 : 0.42;
  } else if (ids.length > 0 && direction) {
    affected = ids;
    type = /\b(keep out|avoid|not in|out of)\b/.test(lower) ? "FORBID_REGION" : "PREFER_REGION";
    confidence = 0.86;
  } else if (ids.length > 0) {
    affected = ids;
    type = "UNCLEAR";
    confidence = 0.45; // knows WHAT, not WHERE
  } else if (direction) {
    type = "PREFER_REGION";
    confidence = 0.38; // knows WHERE, not WHAT
  }

  const affectedSet = new Set(affected);
  const W = graph.die.width;
  const H = graph.die.height;
  const regionFor = (d: Direction | null): RegionBoundingBox => {
    switch (d) {
      case "left":
        return { x_min: 0, y_min: 0, x_max: W * 0.3, y_max: H };
      case "right":
        return { x_min: W * 0.7, y_min: 0, x_max: W, y_max: H };
      case "up":
        return { x_min: 0, y_min: H * 0.7, x_max: W, y_max: H };
      case "down":
        return { x_min: 0, y_min: 0, x_max: W, y_max: H * 0.3 };
      default:
        return { x_min: W * 0.3, y_min: H * 0.3, x_max: W * 0.7, y_max: H * 0.7 };
    }
  };

  const constraint: ConstraintObject = {
    constraint_id: uuidLike(),
    source_request: text,
    frozen_node_ids: graph.nodes.filter((n) => !affectedSet.has(n.node_id)).map((n) => n.node_id),
    affected_node_ids: affected,
    constraint_type: type,
    reference:
      referenceNode !== null
        ? { type: "NODE", value: referenceNode }
        : direction
          ? { type: "REGION", value: regionFor(direction) }
          : { type: "NODE", value: 0 },
    strength: type === "FORBID_REGION" ? "HARD" : "SOFT",
    confidence,
  };
  return { constraint, direction, referenceNode };
}

export function clarificationMessage(instruction: string, c: ConstraintObject): string {
  return (
    `Instruction '${instruction}' was ambiguous or low confidence (${c.confidence.toFixed(2)}). ` +
    `Please specify target macro names or direction explicitly (e.g. 'move macro 3 toward the left edge' ` +
    `or 'move macros 2, 5 away from macro 0').`
  );
}

/** Applies a parsed (confident) constraint. Returns a NEW placement; input untouched. */
export function applyEdit(
  parsed: ParsedInstruction,
  graph: CircuitGraph,
  previous: PlacementJSON,
  seed: number,
): { placement: PlacementJSON; moved: number[] } {
  const placements: PlacementEntry[] = previous.placements.map((p) => ({ ...p }));
  const byId = new Map(placements.map((p) => [p.node_id, p]));
  const W = graph.die.width;
  const H = graph.die.height;
  const { constraint, direction, referenceNode } = parsed;

  const boxOf = (p: PlacementEntry) => {
    const n = graph.nodes[p.node_id];
    const [w, h] = effectiveDims(n.width, n.height, p.orientation);
    return { w, h };
  };

  for (const id of constraint.affected_node_ids) {
    const p = byId.get(id);
    if (!p) continue;
    const { w, h } = boxOf(p);
    let tx = p.x;
    let ty = p.y;
    if (referenceNode !== null) {
      const ref = byId.get(referenceNode)!;
      const rb = boxOf(ref);
      const rcx = ref.x + rb.w / 2;
      const rcy = ref.y + rb.h / 2;
      let dx = p.x + w / 2 - rcx;
      let dy = p.y + h / 2 - rcy;
      const len = Math.hypot(dx, dy) || 1;
      dx /= len;
      dy /= len;
      const step = Math.min(W, H) * 0.22 * (constraint.constraint_type === "MOVE_AWAY_FROM" ? 1 : -1);
      tx = p.x + dx * step;
      ty = p.y + dy * step;
    } else if (direction) {
      const margin = Math.min(W, H) * 0.02;
      if (direction === "left") tx = margin;
      if (direction === "right") tx = W - w - margin;
      if (direction === "up") ty = H - h - margin;
      if (direction === "down") ty = margin;
      if (direction === "center") {
        tx = W / 2 - w / 2;
        ty = H / 2 - h / 2;
      }
    }
    p.x = Math.round(Math.max(0, Math.min(W - w, tx)));
    p.y = Math.round(Math.max(0, Math.min(H - h, ty)));
  }

  // Resolve macro-macro overlaps introduced by the move: each moved macro
  // goes to the nearest free, in-die spot to where it was asked to go
  // (expanding square rings). Frozen macros never move.
  const movedMacros = constraint.affected_node_ids.filter((id) => graph.nodes[id]?.type === "MACRO");
  const settled = placements.filter((q) => graph.nodes[q.node_id].type === "MACRO" && !movedMacros.includes(q.node_id));
  const halo = Math.max(0.5, Math.min(W, H) * 0.004);
  const collides = (x: number, y: number, w: number, h: number) =>
    settled.some((q) => {
      const qb = boxOf(q);
      return x < q.x + qb.w + halo && q.x < x + w + halo && y < q.y + qb.h + halo && q.y < y + h + halo;
    });
  for (const id of movedMacros) {
    const p = byId.get(id)!;
    const { w, h } = boxOf(p);
    const step = Math.max(1, Math.min(w, h) / 4);
    let best: [number, number] | null = collides(p.x, p.y, w, h) ? null : [p.x, p.y];
    const maxR = Math.ceil(Math.max(W, H) / step);
    for (let r = 1; r <= maxR && !best; r++) {
      let bestD = Infinity;
      for (let i = -r; i <= r; i++) {
        for (const [dx, dy] of [[i, -r], [i, r], [-r, i], [r, i]] as const) {
          const x = Math.round(p.x + dx * step);
          const y = Math.round(p.y + dy * step);
          if (x < 0 || y < 0 || x + w > W || y + h > H) continue;
          if (collides(x, y, w, h)) continue;
          const d = Math.hypot(x - p.x, y - p.y);
          if (d < bestD) {
            bestD = d;
            best = [x, y];
          }
        }
      }
    }
    if (best) {
      p.x = best[0];
      p.y = best[1];
    }
    settled.push(p);
  }

  const displaced = relocateCoveredCells(graph, placements);
  const moved = [...new Set([...constraint.affected_node_ids, ...displaced])];
  return {
    placement: {
      design_name: previous.design_name,
      placements,
      generation_metadata: { ...previous.generation_metadata, seed, is_legalized: false },
    },
    moved,
  };
}

export function buildDiffReport(
  constraint: ConstraintObject,
  before: PlacementJSON,
  after: PlacementJSON,
  hpwlDelta: number,
  congestionDelta: number,
  allowed: Set<number>,
): DiffReport {
  const moved = [];
  const unexpected: number[] = [];
  for (let i = 0; i < before.placements.length; i++) {
    const a = before.placements[i];
    const b = after.placements[i];
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    if (dx !== 0 || dy !== 0 || a.orientation !== b.orientation) {
      if (allowed.has(a.node_id)) moved.push({ node_id: a.node_id, delta_x: dx, delta_y: dy });
      else unexpected.push(a.node_id);
    }
  }
  return {
    constraint_id: constraint.constraint_id,
    moved_nodes: moved,
    unexpected_moves: unexpected,
    hpwl_delta: hpwlDelta,
    congestion_delta: congestionDelta,
  };
}

export function formatDiffSummary(graph: CircuitGraph, report: DiffReport, hpwlBefore: number): string {
  const macros = report.moved_nodes.filter((m) => graph.nodes[m.node_id]?.type === "MACRO");
  const cells = report.moved_nodes.length - macros.length;
  const pct = hpwlBefore > 0 ? (report.hpwl_delta / hpwlBefore) * 100 : 0;
  const macroPart =
    macros.length === 0
      ? "No macros moved"
      : `Moved ${macros.length} macro${macros.length === 1 ? "" : "s"} (${macros.map((m) => m.node_id).join(", ")})`;
  const cellPart = cells > 0 ? `, re-placed ${cells} displaced standard cell${cells === 1 ? "" : "s"}` : "";
  if (Math.abs(pct) < 0.05) return `${macroPart}${cellPart}. Wirelength essentially unchanged (<0.05%).`;
  const sign = report.hpwl_delta < 0 ? "decreased" : "increased";
  return `${macroPart}${cellPart}. Wirelength ${sign} by ${Math.abs(pct).toFixed(1)}%.`;
}
