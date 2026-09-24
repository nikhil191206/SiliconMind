/**
 * Real HTTP implementation of SiliconMindApi, talking to backend/main.py.
 *
 * - Every call has a client-side timeout. Generation's is deliberately huge
 *   (spec §4.2): the generator's documented ceiling means some designs take
 *   minutes, and we must not time out a legitimate run.
 * - Cancel = abort the fetch. That does NOT stop server-side compute; the UI
 *   is responsible for saying so (see GenerationProgress).
 * - Backend `detail` messages are preserved verbatim (spec §3.1, §9).
 */
import { ApiError, classifyHttpError, extractDetail } from "./errors";
import type {
  CallOptions,
  DraftRTLRequest,
  DraftRTLResponse,
  EditPlacementRequest,
  EditPlacementResponse,
  GeneratePlacementRequest,
  GeneratePlacementResponse,
  SiliconMindApi,
  SynthesizeRTLRequest,
  SynthesizeRTLResponse,
} from "./types";
import type { CircuitGraph } from "../schemas";

export const TIMEOUTS_MS = {
  draftRtl: 2 * 60_000,
  synthesize: 5 * 60_000,
  /** Well above the largest realistic case (70k nodes ≈ 71-96 s measured). */
  generate: 20 * 60_000,
  edit: 20 * 60_000,
} as const;

function joinUrl(base: string, path: string): string {
  if (!base) return path;
  return base.replace(/\/+$/, "") + path;
}

async function postJson<T>(
  baseUrl: string,
  path: string,
  body: unknown,
  timeoutMs: number,
  opts: CallOptions = {},
): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onExternalAbort = () => controller.abort();
  opts.signal?.addEventListener("abort", onExternalAbort, { once: true });

  let res: Response;
  try {
    res = await fetch(joinUrl(baseUrl, path), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (e) {
    window.clearTimeout(timer);
    opts.signal?.removeEventListener("abort", onExternalAbort);
    if (timedOut) {
      throw new ApiError({
        kind: "timeout",
        status: null,
        endpoint: path,
        detail: `No response after ${Math.round(timeoutMs / 60_000)} minutes.`,
      });
    }
    if (opts.signal?.aborted) {
      throw new ApiError({ kind: "aborted", status: null, endpoint: path, detail: "Cancelled by user." });
    }
    throw new ApiError({
      kind: "network",
      status: null,
      endpoint: path,
      detail: e instanceof Error ? e.message : String(e),
    });
  }

  let text: string;
  try {
    text = await res.text();
  } finally {
    window.clearTimeout(timer);
    opts.signal?.removeEventListener("abort", onExternalAbort);
  }

  let parsed: unknown = null;
  if (text) {
    opts.onParsing?.(text.length);
    // Yield a frame so an "Parsing N MB…" label can paint before a long parse.
    if (text.length > 2_000_000) await new Promise((r) => requestAnimationFrame(() => r(null)));
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
  }

  if (!res.ok) {
    const detail = extractDetail(parsed, text.slice(0, 2000));
    throw new ApiError({ kind: classifyHttpError(res.status, detail), status: res.status, endpoint: path, detail });
  }
  if (parsed === null) {
    throw new ApiError({
      kind: "server",
      status: res.status,
      endpoint: path,
      detail: "The backend returned a success status but the body was not valid JSON.",
    });
  }
  return parsed as T;
}

/** Accepts a bare CircuitGraph or `{ circuit_graph }` / `{ graph }` wrappers. */
function normaliseGraph(raw: unknown): CircuitGraph {
  if (raw && typeof raw === "object") {
    const o = raw as Record<string, unknown>;
    if ("nodes" in o && "die" in o) return o as unknown as CircuitGraph;
    if (o.circuit_graph) return o.circuit_graph as CircuitGraph;
    if (o.graph) return o.graph as CircuitGraph;
  }
  throw new ApiError({
    kind: "server",
    status: 200,
    endpoint: "/api/intake/synthesize",
    detail: "Synthesis succeeded but the response did not contain a CircuitGraph.",
  });
}

export function createHttpApi(baseUrl: string): SiliconMindApi {
  return {
    mode: "http",
    draftRtl: (req: DraftRTLRequest, opts?: CallOptions) =>
      postJson<DraftRTLResponse>(baseUrl, "/api/intake/draft-rtl", req, TIMEOUTS_MS.draftRtl, opts),
    synthesize: async (req: SynthesizeRTLRequest, opts?: CallOptions): Promise<SynthesizeRTLResponse> =>
      normaliseGraph(await postJson<unknown>(baseUrl, "/api/intake/synthesize", req, TIMEOUTS_MS.synthesize, opts)),
    generate: (req: GeneratePlacementRequest, opts?: CallOptions) =>
      postJson<GeneratePlacementResponse>(baseUrl, "/api/placement/generate", req, TIMEOUTS_MS.generate, opts),
    edit: (req: EditPlacementRequest, opts?: CallOptions) =>
      postJson<EditPlacementResponse>(baseUrl, "/api/placement/edit", req, TIMEOUTS_MS.edit, opts),
  };
}
