/**
 * Client-side pre-validation for uploads (spec §3.1).
 *
 * A UX nicety only: it catches obvious mistakes (a binary, a placement file
 * uploaded by accident) before a network round-trip. The backend's 400/422
 * responses remain the source of truth for "was this actually valid".
 */

export type UploadKind = "verilog" | "yosys_json" | "circuit_graph_json" | "lef" | "def";

export interface UploadCheck {
  ok: boolean;
  kind: UploadKind | null;
  /** Shown to the user when !ok, or as a note when ok. */
  message: string;
  /** Parsed JSON when kind is a JSON kind. */
  json?: unknown;
}

const MAX_BYTES = 200 * 1024 * 1024;

function looksBinary(text: string): boolean {
  const sample = text.slice(0, 8000);
  let bad = 0;
  for (let i = 0; i < sample.length; i++) {
    const c = sample.charCodeAt(i);
    if (c === 0) return true;
    if (c < 9 || (c > 13 && c < 32)) bad++;
  }
  return sample.length > 0 && bad / sample.length > 0.02;
}

export function detectKindFromName(name: string): UploadKind | null {
  const n = name.toLowerCase();
  if (n.endsWith(".v") || n.endsWith(".sv") || n.endsWith(".vh")) return "verilog";
  if (n.endsWith(".json")) return "yosys_json";
  if (n.endsWith(".lef")) return "lef";
  if (n.endsWith(".def")) return "def";
  return null;
}

export function validateUpload(name: string, size: number, text: string): UploadCheck {
  if (size > MAX_BYTES) {
    return { ok: false, kind: null, message: `File is ${(size / 1e6).toFixed(0)} MB, over the 200 MB upload limit.` };
  }
  const kind = detectKindFromName(name);
  if (!kind) {
    return { ok: false, kind: null, message: "Unsupported file type. Accepted: .v (structural Verilog) or .json (Yosys JSON)." };
  }
  if (kind === "lef" || kind === "def") {
    return {
      ok: false,
      kind,
      message:
        "LEF/DEF upload isn't available via this endpoint yet. The parser exists (modules/intake/parsers/lefdef_parser.py) but /api/intake/synthesize only accepts RTL or Yosys JSON today.",
    };
  }
  if (looksBinary(text)) {
    return { ok: false, kind, message: "This looks like a binary file, not Verilog or JSON text." };
  }
  if (!text.trim()) return { ok: false, kind, message: "The file is empty." };

  if (kind === "verilog") {
    if (!/\bmodule\b/.test(text)) {
      return { ok: false, kind, message: "No `module` declaration found, so this doesn't look like Verilog." };
    }
    if (!/\bendmodule\b/.test(text)) {
      return { ok: false, kind, message: "Found `module` but no `endmodule`; the file may be truncated." };
    }
    return { ok: true, kind, message: "Looks like Verilog." };
  }

  // JSON
  let json: unknown;
  try {
    json = JSON.parse(text);
  } catch (e) {
    return { ok: false, kind, message: `Not valid JSON: ${e instanceof Error ? e.message : String(e)}` };
  }
  if (json && typeof json === "object") {
    const o = json as Record<string, unknown>;
    if ("placements" in o && "generation_metadata" in o) {
      return {
        ok: false,
        kind,
        message: "This is a PlacementJSON (a generator output), not a netlist. Upload a Yosys JSON netlist instead.",
      };
    }
    if ("modules" in o) return { ok: true, kind: "yosys_json", message: "Looks like Yosys JSON.", json };
    if ("nodes" in o && "hyperedges" in o && "die" in o) {
      return { ok: true, kind: "circuit_graph_json", message: "Looks like a CircuitGraph JSON.", json };
    }
  }
  return {
    ok: false,
    kind,
    message: "JSON parsed, but it has no top-level `modules` key, so it doesn't look like Yosys output.",
  };
}
