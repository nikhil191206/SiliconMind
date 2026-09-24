/**
 * TEMPORARY DEMO FALLBACK (see FALLBACK.md at the repo root).
 *
 * Talks to the Python fallback server in /fallback. Everything fallback-only
 * in the frontend lives in src/fallback/; the handful of lines that mount it
 * elsewhere are tagged `FALLBACK-REMOVE`. Delete both once backend/main.py is
 * real.
 *
 * The fallback server returns an extra `fallback_report` on generate/edit
 * (scores computed by shared/metrics, never put into `metrics`, which stays
 * null because nothing was verified). The spec'd response types don't have
 * that field, so instead of widening them we capture it here in a WeakMap
 * keyed by the placement object the reducer stores by reference.
 */
import type { CircuitGraph, PlacementJSON } from "../lib/schemas";
import type { SiliconMindApi } from "../lib/api/types";

export interface FallbackScore {
  hpwl: number;
  legality_violations: number;
}

export interface FallbackReport extends FallbackScore {
  mode: "fallback";
  method: string;
  scored_by: string;
  congestion_overflow: null;
  congestion_note: string;
  runtime_seconds: number;
  stage_seconds: Record<string, number>;
  baseline: FallbackScore & { name: string };
  /** Edit responses only: the previous placement, scored the same way. */
  before?: FallbackScore;
}

export interface FallbackStatus {
  fallback: true;
  version: string;
  yosys: string | null;
  real: string[];
  substituted: string[];
  not_run: string[];
}

export interface FallbackSample {
  id: string;
  label: string;
  description: string;
}

const reports = new WeakMap<PlacementJSON, FallbackReport>();
let active = false;

/** True once /api/fallback/status answered. Used to skip the BYOK prompt (no LLM is called). */
export function isFallbackActive(): boolean {
  return active;
}

export function fallbackReportFor(p: PlacementJSON | null | undefined): FallbackReport | null {
  return (p && reports.get(p)) ?? null;
}

function url(base: string, path: string): string {
  return base ? base.replace(/\/+$/, "") + path : path;
}

/** null = not a fallback server (the real backend has no /api/fallback/*). */
export async function fetchFallbackStatus(baseUrl: string, signal?: AbortSignal): Promise<FallbackStatus | null> {
  try {
    const res = await fetch(url(baseUrl, "/api/fallback/status"), { signal });
    if (!res.ok) return (active = false), null;
    const body = (await res.json()) as FallbackStatus;
    active = body?.fallback === true;
    return active ? body : null;
  } catch {
    active = false;
    return null;
  }
}

export async function fetchFallbackSamples(baseUrl: string): Promise<FallbackSample[]> {
  const res = await fetch(url(baseUrl, "/api/fallback/samples"));
  if (!res.ok) throw new Error(`Samples request failed (${res.status}).`);
  return (await res.json()) as FallbackSample[];
}

export async function fetchFallbackSample(baseUrl: string, id: string): Promise<CircuitGraph> {
  const res = await fetch(url(baseUrl, `/api/fallback/samples/${encodeURIComponent(id)}`));
  if (!res.ok) throw new Error(`Sample '${id}' failed to load (${res.status}).`);
  return (await res.json()) as CircuitGraph;
}

/** Wraps the HTTP client so fallback_report rides along with each placement. */
export function withFallbackCapture(api: SiliconMindApi): SiliconMindApi {
  return {
    ...api,
    mode: api.mode,
    async generate(req, opts) {
      const res = await api.generate(req, opts);
      const report = (res as { fallback_report?: FallbackReport }).fallback_report;
      if (report && res.placement) reports.set(res.placement, report);
      return res;
    },
    async edit(req, opts) {
      const res = await api.edit(req, opts);
      const report = (res as { fallback_report?: FallbackReport }).fallback_report;
      if (report && res.new_placement) reports.set(res.new_placement, report);
      return res;
    },
  };
}
