/**
 * Qualitative generation-time estimate (spec §4.2).
 *
 * Deliberately NOT a numeric ETA or a percentage: the backend gives no
 * progress events. The buckets are calibrated to the generator's own measured
 * numbers in modules/generator/network.py / NOTES.md:
 *   12,752 nodes ≈ 2.5 s     70,000 nodes ≈ 71-96 s     ~150k = documented ceiling zone
 */
export interface GenerationEstimate {
  label: string;
  detail: string;
  tier: "small" | "medium" | "large" | "extreme";
}

export function estimateGeneration(nodeCount: number): GenerationEstimate {
  if (nodeCount <= 20_000) {
    return {
      tier: "small",
      label: "a few seconds",
      detail: "Measured: a 12,752-node design (ibm01) generates in about 2.5 s.",
    };
  }
  if (nodeCount <= 100_000) {
    return {
      tier: "medium",
      label: "under two minutes",
      detail: "Measured: ~70,000 nodes took 71-96 s on the reference GPU.",
    };
  }
  if (nodeCount <= 150_000) {
    return {
      tier: "large",
      label: "several minutes (this is a large design)",
      detail: "This is inside the generator's documented scalability ceiling zone (70k-150k nodes).",
    };
  }
  return {
    tier: "extreme",
    label: "a very long time, and it may not complete",
    detail:
      "This design is beyond the generator's measured ceiling. modules/generator/NOTES.md documents that designs this large may not currently finish on constrained hardware.",
  };
}
