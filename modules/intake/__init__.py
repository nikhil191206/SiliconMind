"""Intake module package — Person D.

Handles LLM-assisted RTL drafting and Yosys synthesis for the beginner path,
converting hardware descriptions or Verilog RTL into CircuitGraph JSON.
"""

from modules.intake.llm_rtl import (
    LLMConfigurationError,
    synthesize_from_description,
)
from modules.intake.yosys_synthesis import (
    YosysNotInstalledError,
    YosysSynthesisError,
    parse_yosys_json,
    run_yosys_synthesis,
)

__all__ = [
    "synthesize_from_description",
    "run_yosys_synthesis",
    "parse_yosys_json",
    "LLMConfigurationError",
    "YosysNotInstalledError",
    "YosysSynthesisError",
]
