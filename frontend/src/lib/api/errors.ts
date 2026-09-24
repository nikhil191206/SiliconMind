/**
 * Error classification, mapped 1:1 to FRONTEND_SPEC.md §9.
 *
 * Rule: the backend's own `detail` message is always kept and shown verbatim.
 * `kind` only decides the framing around it (e.g. "this is an environment
 * problem, not your file"), never replaces it with a generic message.
 */

export type ApiErrorKind =
  | "llm_config" // 400 LLMConfigurationError, missing/invalid API key
  | "yosys_missing" // 503 YosysNotInstalledError, deployment problem
  | "yosys_synthesis" // 422 YosysSynthesisError, real error in user's RTL
  | "invalid_coordinates" // 500 GenerationProducedInvalidCoordinatesError, generator bug
  | "validation" // other 4xx
  | "server" // other 5xx
  | "timeout" // client-side timeout hit
  | "aborted" // user cancelled
  | "network"; // no response at all

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  /** The backend's `detail` verbatim, or our own honest description if none. */
  readonly detail: string;
  readonly endpoint: string;

  constructor(opts: { kind: ApiErrorKind; status: number | null; detail: string; endpoint: string }) {
    super(opts.detail);
    this.name = "ApiError";
    this.kind = opts.kind;
    this.status = opts.status;
    this.detail = opts.detail;
    this.endpoint = opts.endpoint;
  }
}

/** FastAPI puts messages in `detail`, which may be a string or a list of validation errors. */
export function extractDetail(body: unknown, fallbackText: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      return d
        .map((item) => {
          if (item && typeof item === "object" && "msg" in item) {
            const loc = Array.isArray((item as { loc?: unknown }).loc)
              ? ((item as { loc: unknown[] }).loc.join(".") + ": ")
              : "";
            return loc + String((item as { msg: unknown }).msg);
          }
          return JSON.stringify(item);
        })
        .join("\n");
    }
    return JSON.stringify(d);
  }
  return fallbackText || "The server returned an error with no message body.";
}

export function classifyHttpError(status: number, detail: string): ApiErrorKind {
  const d = detail.toLowerCase();
  if (d.includes("llmconfiguration") || (status === 400 && d.includes("api key"))) return "llm_config";
  if (status === 503 && d.includes("yosys")) return "yosys_missing";
  if (d.includes("yosysnotinstalled")) return "yosys_missing";
  if (status === 422 && d.includes("yosys")) return "yosys_synthesis";
  if (d.includes("invalidcoordinates") || d.includes("invalid coordinates")) return "invalid_coordinates";
  if (status === 400 && d.includes("llm")) return "llm_config";
  if (status >= 500) return "server";
  return "validation";
}

/** The framing line shown above the verbatim detail. Never replaces it. */
export function errorHeadline(err: ApiError): string {
  switch (err.kind) {
    case "llm_config":
      return "Your LLM API key is missing or was rejected.";
    case "yosys_missing":
      return "Synthesis unavailable: the backend's Yosys toolchain isn't installed.";
    case "yosys_synthesis":
      return "Yosys could not synthesize this RTL.";
    case "invalid_coordinates":
      return "Placement generation failed internally.";
    case "timeout":
      return "The request timed out.";
    case "aborted":
      return "Request cancelled.";
    case "network":
      return "Could not reach the backend.";
    case "server":
      return `The backend returned an error (HTTP ${err.status}).`;
    case "validation":
      return `The backend rejected the request (HTTP ${err.status}).`;
  }
}

/** Framing-level explanation: whose problem is this, and what can be done. */
export function errorGuidance(err: ApiError): string | null {
  switch (err.kind) {
    case "llm_config":
      return "Open Settings and paste a valid key. Keys are kept only in this browser.";
    case "yosys_missing":
      return "This is a deployment/environment problem on the server, not a problem with your file.";
    case "yosys_synthesis":
      return "The message below comes straight from Yosys and points at the problem in your RTL.";
    case "invalid_coordinates":
      return "This indicates a generator bug, not something you can fix from your input. Please copy the diagnostics and report it.";
    case "timeout":
      return "This design may be too large for the current backend to place in a reasonable time. See the generator's known scalability limits (modules/generator/NOTES.md).";
    case "network":
      return "Check that the backend is running (default: http://localhost:8000), or switch to Demo mode in Settings.";
    default:
      return null;
  }
}
