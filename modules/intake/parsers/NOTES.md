# Intake Parsers — Notes

Real, verified ingestion parsers for every real dataset actually usable so
far (TECHNICAL.md Section 1.13). Each was built against and validated on
the real downloaded files, not assumed to work from documentation alone.

## Coverage (all validated against 100% of the real designs available, not a sample)

| Source | Parser | Real designs | Result |
|---|---|---|---|
| ISPD02 | `lefdef_parser.py` | 18/18 | 0 failures, 12,752–210,613 nodes each |
| ISPD2015 | `lefdef_parser.py` (multi-LEF) | 16/16 | 0 failures, 28,920–1,285,615 nodes each |
| Ariane (Circuit Training) | `protobuf_parser.py` | 1/1 | 133 real macros, 2,163 nodes |
| CircuitNet 3.0 | `circuitnet_parser.py` | 2004/2004 | 0 failures |

## CircuitNet: real data availability finding (2026-09-22)

TECHNICAL.md Section 1.14.2 originally planned to pretrain the encoders on
CircuitNet's congestion/wirelength labels, which requires real physical
placement (macro/cell x/y, and therefore real width/height). That data is
**not currently publicly available** — confirmed directly against
CircuitNet 3.0's own HuggingFace page
(huggingface.co/datasets/SKLP-EDA-LAB/CircuitNet3.0), which explicitly
states layout/LEF-DEF artifacts "are not yet available" (being uploaded
incrementally; the maintainers ask to be contacted directly for specific
layout packages). This was independently confirmed by inspecting the real
cell names actually present (`DFFHQX1`, `AND2X1`, `BUFX12` — no
underscore) against the real, open NanGate45 LEF we do have (`DFF_X1`,
`AND2_X1` — underscore-separated): they don't match, so CircuitNet 3.0
uses a different (likely commercial) cell library we have no LEF for
either way.

**What CircuitNet 3.0 genuinely does provide, confirmed real and complete**
(not sampled): a real structural (post-P&R, Cadence-Innovus-generated)
gate-level netlist per design (`final_netlist.v`), and real per-instance
static-timing-analysis data (`feature.json`) — verified 100% instance
coverage (every instance in the netlist has a matching real feature.json
entry) across all 2,004 real downloaded designs.

**What this project does about it, rather than fabricate the missing
geometry:** `circuitnet_parser.py` produces a `PretrainingGraph`
(`shared/schemas/pretraining_graph.py`) — a deliberately separate schema
from `CircuitGraph`, since `CircuitGraph.width`/`.height` are required
positive fields that CircuitNet cannot honestly satisfy. The pretraining
task itself changed to match what's real: predict actual timing slack
(only sequential/flip-flop cells carry a real slack value in a normal STA
report — confirmed 16/357 real labeled nodes in one sample design, a real
and expected sparsity, not a parsing bug) from real graph structure plus
real per-cell electrical scalars (drive strength, fanout load/res),
instead of congestion. See `modules/encoders/pretraining_model.py` and
`experiments/pretrain_encoder_circuitnet.py`.

This is a real, documented deviation from TECHNICAL.md's original plan,
forced by public data availability — not something to silently work around
or paper over. If a matching real cell LEF or CircuitNet's layout data
becomes available later, this is the one place that would need revisiting.
