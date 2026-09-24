/**
 * Minimal tokenizer for Verilog syntax highlighting: no dependency, and the
 * output is rendered inside real <pre><code> (spec §10 a11y requirement).
 */

export type TokenKind = "kw" | "type" | "num" | "str" | "com" | "punc" | "plain";

export interface Token {
  kind: TokenKind;
  text: string;
}

const VERILOG_KEYWORDS = new Set(
  (
    "module endmodule input output inout parameter localparam assign always always_ff always_comb " +
    "begin end if else case casez casex endcase default for while generate endgenerate genvar " +
    "function endfunction task endtask posedge negedge or and not initial"
  ).split(" "),
);
const VERILOG_TYPES = new Set("wire reg logic integer signed unsigned supply0 supply1 tri".split(" "));

const TOKEN_RE =
  /(\/\/[^\n]*|\/\*[\s\S]*?\*\/)|("(?:[^"\\]|\\.)*")|(\d+'[sS]?[bBoOdDhH][0-9a-fA-FxXzZ_?]+|\b\d[\d_]*(?:\.\d+)?\b)|([A-Za-z_$][\w$]*)|([()[\]{};:,.=<>!&|^~+\-*/%?@#])|(\s+)|(.)/g;

export function tokenizeVerilog(src: string): Token[] {
  const out: Token[] = [];
  let m: RegExpExecArray | null;
  TOKEN_RE.lastIndex = 0;
  while ((m = TOKEN_RE.exec(src))) {
    if (m[1]) out.push({ kind: "com", text: m[1] });
    else if (m[2]) out.push({ kind: "str", text: m[2] });
    else if (m[3]) out.push({ kind: "num", text: m[3] });
    else if (m[4]) {
      const w = m[4];
      out.push({ kind: VERILOG_KEYWORDS.has(w) ? "kw" : VERILOG_TYPES.has(w) ? "type" : "plain", text: w });
    } else if (m[5]) out.push({ kind: "punc", text: m[5] });
    else out.push({ kind: "plain", text: m[0] });
  }
  return out;
}
