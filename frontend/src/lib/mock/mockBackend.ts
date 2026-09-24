/**
 * DEMO MODE ONLY: an in-browser implementation of SiliconMindApi.
 *
 * Why this exists: backend/main.py isn't written yet (FRONTEND_SPEC.md §14),
 * and every UI state in the spec still needs to be built and seen. The app
 * shows a permanent "Demo mode" strip whenever this is active, and every
 * placement it produces carries a model_variant that says it's a mock.
 *
 * `scenario` lets a developer force each §9 error/contradiction path on
 * purpose, so those loud states can be designed and verified before real
 * backend bugs ever produce them.
 */
import { ApiError } from "../api/errors";
import type {
  CallOptions,
  DraftRTLRequest,
  EditPlacementRequest,
  EditPlacementResponse,
  GeneratePlacementRequest,
  GeneratePlacementResponse,
  SiliconMindApi,
  SynthesizeRTLRequest,
} from "../api/types";
import type { CircuitGraph, MetricsObject, PlacementJSON } from "../schemas";
import { constraintRequiresClarification } from "../schemas";
import { hashString } from "../random";
import { makeSyntheticGraph } from "./mockGraphs";
import { computeMetrics } from "./mockMetrics";
import { generateDemoPlacement } from "./mockPlacer";
import { applyEdit, buildDiffReport, clarificationMessage, formatDiffSummary, parseInstruction } from "./mockEditor";
import { draftRtlFromDescription } from "./mockRtl";

export type DemoScenario =
  | "verified"
  | "unverified"
  | "legality_contradiction"
  | "unexpected_moves"
  | "generator_crash"
  | "yosys_missing"
  | "yosys_error"
  | "llm_key_rejected";

export const DEMO_SCENARIOS: Array<{ id: DemoScenario; label: string; description: string }> = [
  { id: "verified", label: "Happy path", description: "Placements come back verified with metrics." },
  { id: "unverified", label: "Legalizer unavailable", description: "verification_status = \"unavailable: …\", metrics null." },
  {
    id: "legality_contradiction",
    label: "Contradiction: verified + violations",
    description: "\"verified\" but legality_violations > 0 → internal-inconsistency state.",
  },
  {
    id: "unexpected_moves",
    label: "Contradiction: unexpected moves",
    description: "Edits return non-empty diff_report.unexpected_moves.",
  },
  { id: "generator_crash", label: "Generator crash (500)", description: "GenerationProducedInvalidCoordinatesError." },
  { id: "yosys_missing", label: "Yosys not installed (503)", description: "Synthesis unavailable on the server." },
  { id: "yosys_error", label: "Yosys synthesis error (422)", description: "Synthesis rejects the RTL." },
  { id: "llm_key_rejected", label: "LLM key rejected (400)", description: "LLMConfigurationError on LLM calls." },
];

function delay(ms: number, signal?: AbortSignal, endpoint = ""): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new ApiError({ kind: "aborted", status: null, endpoint, detail: "Cancelled by user." }));
      return;
    }
    const t = window.setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        window.clearTimeout(t);
        reject(new ApiError({ kind: "aborted", status: null, endpoint, detail: "Cancelled by user." }));
      },
      { once: true },
    );
  });
}

function sizeFromText(text: string): { macros: number; cells: number } {
  const h = hashString(text);
  const regs = (text.match(/\breg\b/g) ?? []).length;
  const assigns = (text.match(/\bassign\b|<=/g) ?? []).length;
  return {
    macros: 4 + (h % 9) + Math.min(8, Math.floor(regs / 2)),
    cells: 1_200 + ((h >>> 8) % 3_000) + assigns * 40,
  };
}

export function createDemoApi(getScenario: () => DemoScenario): SiliconMindApi {
  return {
    mode: "demo",

    async draftRtl(req: DraftRTLRequest, opts?: CallOptions) {
      const endpoint = "/api/intake/draft-rtl";
      await delay(900 + Math.random() * 600, opts?.signal, endpoint);
      if (getScenario() === "llm_key_rejected") {
        throw new ApiError({
          kind: "llm_config",
          status: 400,
          endpoint,
          detail: "LLMConfigurationError: the provider rejected the API key (401 Unauthorized).",
        });
      }
      return { rtl_code: draftRtlFromDescription(req.description) };
    },

    async synthesize(req: SynthesizeRTLRequest, opts?: CallOptions) {
      const endpoint = "/api/intake/synthesize";
      await delay(700 + Math.random() * 700, opts?.signal, endpoint);
      const scenario = getScenario();
      if (scenario === "yosys_missing") {
        throw new ApiError({
          kind: "yosys_missing",
          status: 503,
          endpoint,
          detail: "YosysNotInstalledError: `yosys` executable not found on PATH.",
        });
      }
      if (req.yosys_json_data && typeof req.yosys_json_data === "object") {
        const o = req.yosys_json_data as Record<string, unknown>;
        if ("nodes" in o && "die" in o && "hyperedges" in o) {
          return { ...(o as unknown as CircuitGraph), design_name: req.design_name };
        }
        const modules = (o.modules ?? {}) as Record<string, { cells?: Record<string, unknown> }>;
        const cellCount = Object.values(modules).reduce((s, m) => s + Object.keys(m.cells ?? {}).length, 0);
        return makeSyntheticGraph({
          designName: req.design_name,
          macros: Math.max(2, Math.min(40, Math.round(cellCount / 400))),
          stdCells: Math.max(50, cellCount),
          seed: hashString(req.design_name),
        });
      }
      const rtl = req.rtl_code ?? "";
      if (scenario === "yosys_error" || !/\bmodule\b/.test(rtl) || !/\bendmodule\b/.test(rtl)) {
        const line = Math.max(1, rtl.split("\n").length - 1);
        throw new ApiError({
          kind: "yosys_synthesis",
          status: 422,
          endpoint,
          detail: `YosysSynthesisError: ERROR: design.v:${line}: syntax error, unexpected end of file, expecting endmodule`,
        });
      }
      const size = sizeFromText(rtl);
      return makeSyntheticGraph({
        designName: req.design_name,
        macros: size.macros,
        stdCells: size.cells,
        seed: hashString(req.design_name + rtl),
      });
    },

    async generate(req: GeneratePlacementRequest, opts?: CallOptions): Promise<GeneratePlacementResponse> {
      const endpoint = "/api/placement/generate";
      const n = req.graph.nodes.length;
      await delay(900 + Math.min(4000, n * 0.02), opts?.signal, endpoint);
      const scenario = getScenario();
      if (scenario === "generator_crash") {
        throw new ApiError({
          kind: "invalid_coordinates",
          status: 500,
          endpoint,
          detail:
            "GenerationProducedInvalidCoordinatesError: 37 of 1,204 nodes had non-finite coordinates after the final ODE step (seed=" +
            req.seed +
            ").",
        });
      }
      const t0 = performance.now();
      const placement = generateDemoPlacement(req.graph, req.seed);
      const runtime = (performance.now() - t0) / 1000;
      return this.finalize(placement, req.graph, runtime, scenario);
    },

    async edit(req: EditPlacementRequest, opts?: CallOptions): Promise<EditPlacementResponse> {
      const endpoint = "/api/placement/edit";
      await delay(800 + Math.min(3000, req.graph.nodes.length * 0.015), opts?.signal, endpoint);
      const scenario = getScenario();
      if (scenario === "llm_key_rejected") {
        throw new ApiError({
          kind: "llm_config",
          status: 400,
          endpoint,
          detail: "LLMConfigurationError: the provider rejected the API key (401 Unauthorized).",
        });
      }
      const parsed = parseInstruction(req.instruction, req.graph);
      if (constraintRequiresClarification(parsed.constraint)) {
        return {
          requires_clarification: true,
          clarification_message: clarificationMessage(req.instruction, parsed.constraint),
          constraint: parsed.constraint,
          new_placement: null,
          metrics_before: null,
          metrics_after: null,
          verification_status: null,
          diff_report: null,
          diff_summary: null,
        };
      }
      const t0 = performance.now();
      const { placement, moved } = applyEdit(parsed, req.graph, req.previous_placement, req.seed);
      if (scenario === "unexpected_moves") {
        // Simulate a freeze-enforcement bug: nudge two frozen nodes.
        const frozen = parsed.constraint.frozen_node_ids.slice(0, 2);
        for (const id of frozen) placement.placements[id].x += 1;
      }
      const runtime = (performance.now() - t0) / 1000;
      const before = this.finalize(req.previous_placement, req.graph, runtime, scenario);
      const after = this.finalize(placement, req.graph, runtime, scenario);
      // DiffReport deltas come from the metric formulas applied to both
      // placements (as C's shared/metrics would), independent of whether the
      // legalizer verified them, never from a null metrics object.
      const rawBefore = computeMetrics(req.previous_placement, req.graph, 0);
      const rawAfter = computeMetrics(placement, req.graph, 0);
      const hpwlBefore = rawBefore.hpwl;
      const report = buildDiffReport(
        parsed.constraint,
        req.previous_placement,
        after.placement,
        rawAfter.hpwl - rawBefore.hpwl,
        rawAfter.congestion_overflow - rawBefore.congestion_overflow,
        new Set(moved),
      );
      const status =
        before.verification_status === after.verification_status
          ? after.verification_status
          : `before: ${before.verification_status}; after: ${after.verification_status}`;
      return {
        requires_clarification: false,
        clarification_message: null,
        constraint: parsed.constraint,
        new_placement: after.placement,
        metrics_before: before.metrics,
        metrics_after: after.metrics,
        verification_status: status,
        diff_report: report,
        diff_summary: formatDiffSummary(req.graph, report, hpwlBefore),
      };
    },

    // Not part of SiliconMindApi, internal helper mimicking backend _legalize().
    finalize(
      placement: PlacementJSON,
      graph: CircuitGraph,
      runtime: number,
      scenario: DemoScenario,
    ): GeneratePlacementResponse {
      if (scenario === "unverified") {
        return {
          placement,
          metrics: null,
          verification_status: "unavailable: demo mode, DREAMPlace/OpenROAD are not connected",
        };
      }
      const metrics: MetricsObject = computeMetrics(placement, graph, runtime);
      if (scenario === "legality_contradiction") {
        metrics.legality_violations = Math.max(3, metrics.legality_violations);
      } else if (metrics.legality_violations > 0) {
        // A real legalizer would have fixed or refused this; the mock can't,
        // so it honestly reports the placement as unverifiable.
        return {
          placement,
          metrics: null,
          verification_status: `unavailable: demo placer could not produce a legal placement (${metrics.legality_violations} violations)`,
        };
      }
      return {
        placement: { ...placement, generation_metadata: { ...placement.generation_metadata, is_legalized: true } },
        metrics,
        verification_status: "verified",
      };
    },
  } as SiliconMindApi & {
    finalize(p: PlacementJSON, g: CircuitGraph, r: number, s: DemoScenario): GeneratePlacementResponse;
  };
}
