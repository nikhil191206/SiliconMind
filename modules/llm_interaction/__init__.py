"""LLM Interaction module package — Person D.

Handles natural-language constraint parsing (NL text -> ConstraintObject)
and placement diff reporting (before/after PlacementJSON -> DiffReport).
"""

from modules.llm_interaction.constraint_parser import parse_constraint
from modules.llm_interaction.diff_report import format_diff_summary, generate_diff_report

__all__ = [
    "parse_constraint",
    "generate_diff_report",
    "format_diff_summary",
]
