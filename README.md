# chip-placement-system

AI-driven chip placement: netlist encoders (GCN/GAT/DE-HNN/DeepGate4) condition a
flow-matching/diffusion placement generator, verified against DREAMPlace/OpenROAD
and an RL baseline, with a natural-language iterative-editing layer on top.

- Technical specification (binding, authoritative): [TECHNICAL.md](TECHNICAL.md)
- Work distribution across the four owners: [workDistribution.md](workDistribution.md)
- Execution plan / bootstrap order: [INSTRUCTIONS.md](INSTRUCTIONS.md)
- Environment setup: [environment_setup.md](environment_setup.md)
- Dataset download checklist: [data/README.md](data/README.md)
- Contribution / branching rules: [CONTRIBUTING.md](CONTRIBUTING.md)

See `TECHNICAL.md` Section 2 for the full repository layout and Section 3 for the
exact data contracts between modules.
