"""LLM-Assisted RTL Drafting — TECHNICAL.md Section 4.D / Section 3.4.

Owned by Person D.
Translates a beginner's natural-language hardware/design description into synthesizable RTL (Verilog HDL text).

Distinguishes LLM generation from deterministic RTL validation and Yosys synthesis.
Does NOT claim RTL is valid merely because the LLM returned it.
"""

import re
from typing import Optional

# Standard fallback templates for beginner hardware descriptions when LLM API key is absent or offline.
_FALLBACK_TEMPLATES = {
    "counter": """module counter (
    input wire clk,
    input wire rst,
    input wire enable,
    output reg [7:0] count
);
    always @(posedge clk or posedge rst) begin
        if (rst)
            count <= 8'b0;
        else if (enable)
            count <= count + 1'b1;
    end
endmodule
""",
    "adder": """module adder (
    input wire [7:0] a,
    input wire [7:0] b,
    output wire [8:0] sum
);
    assign sum = a + b;
endmodule
""",
    "alu": """module alu (
    input wire [7:0] a,
    input wire [7:0] b,
    input wire [1:0] op,
    output reg [7:0] result
);
    always @(*) begin
        case (op)
            2'b00: result = a + b;
            2'b01: result = a - b;
            2'b10: result = a & b;
            2'b11: result = a | b;
            default: result = 8'b0;
        endcase
    end
endmodule
""",
    "and_or": """module and_or_gate (
    input wire a,
    input wire b,
    input wire c,
    output wire out
);
    assign out = (a & b) | c;
endmodule
""",
}


class LLMConfigurationError(Exception):
    """Raised when LLM API credentials or configuration are missing when required."""


class RTLValidationError(Exception):
    """Raised when generated RTL fails basic structural/syntax checks."""


def extract_verilog_code(raw_text: str) -> str:
    """Safely extracts Verilog HDL code from LLM response text,

    stripping markdown code blocks (```verilog ... ``` or ``` ... ```) if present.
    """
    if not raw_text or not raw_text.strip():
        raise RTLValidationError("LLM response was empty.")

    # Match ```verilog ... ``` or ```v ... ``` or ``` ... ```
    pattern = r"```(?:verilog|v|systemverilog)?\s*\n?(.*?)```"
    matches = re.findall(pattern, raw_text, re.DOTALL | re.IGNORECASE)

    if matches:
        extracted = matches[0].strip()
    else:
        extracted = raw_text.strip()

    # Basic Verilog structural validation check
    if "module" not in extracted or "endmodule" not in extracted:
        raise RTLValidationError(
            "Extracted RTL lacks essential 'module' or 'endmodule' declaration."
        )

    return extracted


def synthesize_from_description(
    description: str,
    template: Optional[str] = None,
    api_key: Optional[str] = None,
    provider: str = "openai",
) -> str:
    """Translates a natural language description into synthesizable Verilog RTL.

    Args:
        description: Natural language hardware description.
        template: Optional fallback template name (e.g. 'counter', 'adder', 'alu', 'and_or').
        api_key: Optional API key. If not provided, checks OPENAI_API_KEY environment variable.
        provider: LLM provider name ("openai", "anthropic", etc.).

    Returns:
        Synthesizable Verilog HDL string.

    Raises:
        LLMConfigurationError: If no API key is available and template matching fails.
        RTLValidationError: If extracted RTL is malformed.
    """
    description_clean = description.strip().lower()

    from shared.llm_client import NoLLMCredentialsError, resolve_llm_client

    try:
        resolved = resolve_llm_client(api_key)
    except NoLLMCredentialsError:
        # No LLM credentials at all: check if template requested or
        # description matches a known offline fallback keyword.
        for key, rtl_code in _FALLBACK_TEMPLATES.items():
            if (template and template.lower() == key) or (key in description_clean):
                return rtl_code

        raise LLMConfigurationError(
            "No LLM API key configured (GROQ_API_KEY or OPENAI_API_KEY/LLM_API_KEY required) "
            "and description did not match an offline fallback template. "
            "To use online LLM RTL drafting, set one of those in your environment."
        )

    # Call the resolved LLM provider (Groq or OpenAI) for a real completion.
    try:
        prompt = (
            "You are an expert Verilog digital design engineer. "
            "Write clean, standard, synthesizable Verilog HDL code based on the following description. "
            "Output ONLY the synthesizable Verilog code inside a ```verilog markdown block. "
            "Do not include explanation prose before or after the code block.\n\n"
            f"Description: {description}"
        )

        response = resolved.client.chat.completions.create(
            model=resolved.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )

        raw_output = response.choices[0].message.content or ""
        return extract_verilog_code(raw_output)

    except Exception as exc:
        if isinstance(exc, (LLMConfigurationError, RTLValidationError)):
            raise
        # Fallback to local template match if the live LLM API call itself fails
        # (network error, rate limit, etc.) -- not if credentials are just absent.
        for key, rtl_code in _FALLBACK_TEMPLATES.items():
            if key in description_clean:
                return rtl_code
        raise RuntimeError(f"LLM RTL generation failed ({resolved.provider}): {exc}") from exc
