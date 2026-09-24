/**
 * DEMO MODE ONLY: stand-in for /api/intake/draft-rtl (LLM RTL drafting).
 * Picks a small, readable template from keywords in the description. The UI
 * still shows the "AI-generated, review before continuing" disclaimer, since
 * the real endpoint's output is LLM text.
 */

function sanitizeIdent(s: string): string {
  const id = s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 32);
  return /^[a-z]/.test(id) ? id : `design_${id || "top"}`;
}

export function draftRtlFromDescription(description: string, designName = "top"): string {
  const d = description.toLowerCase();
  const name = sanitizeIdent(designName);
  const header = `// Drafted from description: "${description.trim().slice(0, 120)}"\n// DEMO MODE: template-based draft, not real LLM output.\n`;

  if (/fifo|queue|buffer/.test(d)) {
    return `${header}module ${name} #(
  parameter WIDTH = 8,
  parameter DEPTH = 16
) (
  input  wire             clk,
  input  wire             rst_n,
  input  wire             wr_en,
  input  wire             rd_en,
  input  wire [WIDTH-1:0] din,
  output reg  [WIDTH-1:0] dout,
  output wire             full,
  output wire             empty
);
  localparam AW = $clog2(DEPTH);
  reg [WIDTH-1:0] mem [0:DEPTH-1];
  reg [AW:0] wptr, rptr;

  assign full  = (wptr[AW] != rptr[AW]) && (wptr[AW-1:0] == rptr[AW-1:0]);
  assign empty = (wptr == rptr);

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      wptr <= 0;
      rptr <= 0;
    end else begin
      if (wr_en && !full) begin
        mem[wptr[AW-1:0]] <= din;
        wptr <= wptr + 1'b1;
      end
      if (rd_en && !empty) begin
        dout <= mem[rptr[AW-1:0]];
        rptr <= rptr + 1'b1;
      end
    end
  end
endmodule
`;
  }

  if (/alu|arithmetic|adder|multipl/.test(d)) {
    return `${header}module ${name} #(
  parameter WIDTH = 16
) (
  input  wire [WIDTH-1:0] a,
  input  wire [WIDTH-1:0] b,
  input  wire [2:0]       op,
  output reg  [WIDTH-1:0] y,
  output wire             zero
);
  always @(*) begin
    case (op)
      3'b000: y = a + b;
      3'b001: y = a - b;
      3'b010: y = a & b;
      3'b011: y = a | b;
      3'b100: y = a ^ b;
      3'b101: y = a << 1;
      3'b110: y = a >> 1;
      default: y = {WIDTH{1'b0}};
    endcase
  end
  assign zero = (y == {WIDTH{1'b0}});
endmodule
`;
  }

  // Default: counter with enable and synchronous clear.
  return `${header}module ${name} #(
  parameter WIDTH = 8
) (
  input  wire             clk,
  input  wire             rst_n,
  input  wire             en,
  input  wire             clear,
  output reg  [WIDTH-1:0] count,
  output wire             wrap
);
  assign wrap = en && (count == {WIDTH{1'b1}});

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      count <= {WIDTH{1'b0}};
    else if (clear)
      count <= {WIDTH{1'b0}};
    else if (en)
      count <= count + 1'b1;
  end
endmodule
`;
}
