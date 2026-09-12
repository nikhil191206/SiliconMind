# Dataset Download Checklist

Per TECHNICAL.md Section 1.13 (sources) and Section 1.16 (exact target folder names).
Update the checkboxes as datasets land — this file is the literal source of truth for
"is X downloaded yet," not a memory or a Slack message.

Never commit the actual downloaded files (`data/raw/*` is gitignored) — only this
checklist and the `.gitkeep` placeholders track state in git.

- [x] **ISPD 2005 Placement Contest Benchmark Suite** → `data/raw/ispd02/`
      (Bookshelf `.nodes`/`.nets`/`.pl`/`.scl`, 16 IBM-derived designs: ibm01-ibm18 etc.)
      Source: https://archive.sigda.org/ispd2005/contest.htm
- [x] **ISPD 2015 Blockage-Aware Placement Contest Benchmark Suite** → `data/raw/ispd2015/`
      (LEF/DEF with fence regions and blockages, e.g. mgc_des_perf_*, mgc_fft_*)
      Source: http://www.ispd.cc/contests/15/web/downloads.html
- [x] **ASAP7 (7nm Predictive Research PDK)** → `data/raw/asap7/`
      (clone with submodules — tech files, asap7sc7p5t_28 stdcell lib, SRAM macros)
      Source: https://github.com/The-OpenROAD-Project/asap7
- [x] **Ariane RISC-V netlist (Google Circuit Training repo)** → `data/raw/ariane_circuit_training/`
      (`netlist.pb.txt` + `initial.plc`)
      Source: https://github.com/google-research/circuit_training
- [x] **TILOS-AI-Institute MacroPlacement repo** → `data/raw/macroplacement/`
      (real testcases: Ariane, BlackParrot, MemPool + SA baseline results + evaluators)
      Source: https://github.com/TILOS-AI-Institute/MacroPlacement
- [x] **CircuitNet** → `data/raw/circuitnet/`
      (CircuitNet-N14 v2.0 / N45 v3.0, via Hugging Face per repo README)
      Source: https://circuitnet.github.io/
- [x] **Open RTL designs (OpenHW CORE-V family)** → `data/raw/corev/`
      (e.g. cv32e40p; clone per-core as needed for beginner-path + generalization split)
      Source: https://github.com/openhwgroup/core-v-cores

## Notes

- `data/processed/` (Circuit Graph JSON cache, TECHNICAL.md Section 3.1) is derived
  from `data/raw/` by code and is never committed or hand-edited. If it's ever out of
  sync with `data/raw/`, delete and regenerate via `data/processed/build_cache.py`.
- Checked above only means the folder is populated — it does not mean the ingestion
  parser for that source has been written/tested yet. Track parser status separately
  in each module's own README/issues.
