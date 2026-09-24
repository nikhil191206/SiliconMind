/**
 * Derived state. The invariant checks here are the heart of spec §0: they
 * turn "a 200 OK with a contradictory body" into a loud error, regardless of
 * HTTP status.
 */
import type { HistoryEntry, SessionState } from "./sessionTypes";

export function currentEntry(s: SessionState): HistoryEntry | null {
  return s.placementHistory[s.currentIndex] ?? null;
}

/** The entry an edit was made FROM (for before/after compare), if any. */
export function parentEntry(s: SessionState): HistoryEntry | null {
  const cur = currentEntry(s);
  if (!cur || cur.parentIndex === null) return null;
  return s.placementHistory[cur.parentIndex] ?? null;
}

export function isVerified(status: string | null | undefined): boolean {
  return status === "verified";
}

/** "unavailable: <reason>" → "<reason>" */
export function unavailableReason(status: string): string {
  const i = status.indexOf(":");
  return i >= 0 ? status.slice(i + 1).trim() : status;
}

export interface InvariantViolation {
  code: "verified_with_legality_violations" | "unexpected_moves";
  title: string;
  explanation: string;
  diagnostic: unknown;
}

export function invariantViolations(s: SessionState): InvariantViolation[] {
  const cur = currentEntry(s);
  if (!cur) return [];
  const out: InvariantViolation[] = [];
  if (isVerified(cur.verificationStatus) && cur.metrics && cur.metrics.legality_violations > 0) {
    out.push({
      code: "verified_with_legality_violations",
      title: "Internal inconsistency detected: verified placement has legality violations",
      explanation: `The backend reported verification_status = "verified" together with legality_violations = ${cur.metrics.legality_violations}. By TECHNICAL.md §1.4 this must be 0 after legalization. This is a bug in an upstream module, not a reportable result. Do not use this placement.`,
      diagnostic: {
        invariant: "legality_violations == 0 when verification_status == 'verified'",
        verification_status: cur.verificationStatus,
        metrics: cur.metrics,
        generation_metadata: cur.placement.generation_metadata,
        design_name: cur.placement.design_name,
        triggering_instruction: cur.triggeringInstruction,
        timestamp: cur.timestamp,
      },
    });
  }
  if (cur.diffReport && cur.diffReport.unexpected_moves.length > 0) {
    out.push({
      code: "unexpected_moves",
      title: `Internal inconsistency detected: ${cur.diffReport.unexpected_moves.length} frozen node(s) moved`,
      explanation:
        "diff_report.unexpected_moves must be empty. Non-empty means the generator's freeze enforcement failed (a bug in Person B's module, TECHNICAL.md §1.7). These moves were not requested and are not an expected part of this edit.",
      diagnostic: {
        invariant: "diff_report.unexpected_moves == []",
        unexpected_moves: cur.diffReport.unexpected_moves,
        constraint: cur.constraint,
        diff_report: cur.diffReport,
        triggering_instruction: cur.triggeringInstruction,
        generation_metadata: cur.placement.generation_metadata,
        timestamp: cur.timestamp,
      },
    });
  }
  return out;
}
