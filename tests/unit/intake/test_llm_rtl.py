"""Unit tests for LLM-assisted RTL drafting (Person D)."""

import pytest

from modules.intake.llm_rtl import (
    LLMConfigurationError,
    RTLValidationError,
    extract_verilog_code,
    synthesize_from_description,
)


def test_extract_verilog_code_markdown_blocks():
    text = """Here is the RTL code:
```verilog
module test (input wire clk);
endmodule
```
Hope this helps!"""
    code = extract_verilog_code(text)
    assert "module test" in code
    assert "endmodule" in code


def test_extract_verilog_code_plain_text():
    text = "module plain (input wire a, output wire b);\n  assign b = a;\nendmodule"
    code = extract_verilog_code(text)
    assert "module plain" in code


def test_extract_verilog_code_invalid_raises():
    with pytest.raises(RTLValidationError):
        extract_verilog_code("This is just prose text with no verilog module.")


def _clear_all_llm_credentials(monkeypatch):
    """Real credentials (GROQ_API_KEY, and possibly OPENAI_API_KEY/LLM_API_KEY)
    may genuinely be configured in this environment via .env — a test of the
    offline/no-credentials fallback path must clear ALL of them, not just
    one, or it silently starts exercising the real LLM call instead (see
    modules/intake/NOTES.md-equivalent discussion in modules/llm_interaction/NOTES.md)."""
    for var in ("GROQ_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_synthesize_from_description_template_fallback(monkeypatch):
    _clear_all_llm_credentials(monkeypatch)
    rtl = synthesize_from_description("Create an 8-bit counter design", template="counter")
    assert "module counter" in rtl
    assert "endmodule" in rtl


def test_synthesize_from_description_missing_key_raises(monkeypatch):
    _clear_all_llm_credentials(monkeypatch)

    with pytest.raises(LLMConfigurationError):
        synthesize_from_description("Some unknown custom complex accelerator circuit description with no key")
