# Person D — LLM Interaction: Notes

Status: `parse_constraint` (LLM-backed with a deterministic offline/no-API-key
heuristic fallback) and `generate_diff_report`/`format_diff_summary` are
implemented and unit-tested (`tests/unit/llm_interaction/`).

## Bug found and fixed during A/B/C/D integration (2026-09-18)

**The heuristic fallback parser's digit-extraction regex, `\b(\d+)\b`, could
not match a digit following an underscore** (`_` counts as a word character
in Python's `re`, so there is no `\b` boundary between `node_` and `0`).
Every example in this file's own docstring — `"Move SRAM_0 away from..."`,
`"Move MACRO_0 closer to MACRO_1"` — uses exactly that underscore-joined
form. In practice this meant `"Move node_0 away from node_1"` extracted zero
digits, silently fell back to "first placed node" for both the moved node
*and* its own reference, and produced a self-referential
`MOVE_AWAY_FROM(node, itself)` constraint at high confidence (0.85) —
never flagged as unclear, and instrumental in producing a NaN placement
once it reached `PlacementGenerator.generate()` (see
`modules/generator/NOTES.md` §5 for the other half of that bug).

**Fix:** digit extraction now matches any run of digits **not immediately
preceded by a letter or digit** (`(?<![a-zA-Z0-9])(\d+)`), so `_`, `#`,
whitespace, and start-of-string all count as valid separators —
`"node_0"`, `"SRAM_0"`, `"macro#1"`, and a bare `"10"` (as in the region
phrasing `"region 10 10 50 50"`) all extract correctly.

**A second, related bug in the same function:** every digit that matched a
valid node id was added to `affected_node_ids` — including a second node
mentioned purely as the *reference point* (e.g. the `node_1` in "away from
node_1"). That reference node should stay frozen like everything else it
isn't the one being moved. Fixed: only the first valid node id becomes
`affected_node_ids`; a second one is used only as `ref_val`, as the
`digits[1]`-based reference logic below it already intended.

Neither bug affected the LLM-backed path (used whenever an API key is
configured) — only the deterministic fallback used in tests and in offline/
no-API-key operation.
