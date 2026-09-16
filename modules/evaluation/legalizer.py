"""legalize_and_score — TECHNICAL.md Section 3.5 / Section 4.C.

The single source of truth for legalization + scoring: wraps DREAMPlace for
legalization (`dreamplace_runner.py`) and OpenROAD for the congestion
estimate (`openroad_runner.py`), then computes all three reportable metrics
via `shared/metrics/` (Section 1.4) — no module downstream of this one may
compute HPWL/congestion/legality independently (Section 3.5).

Both external tools are genuinely not installed in this development
environment (see `dreamplace_runner.py`, `openroad_runner.py`, and
NOTES.md), so calling this function today raises a clear
`DreamplaceNotInstalledError` rather than fabricating a result — exactly
INSTRUCTIONS.md Section 4's "never substitute a placeholder ... in anything
that will be reported as a result." The orchestration logic itself (parsing
DREAMPlace's output, wiring the congestion estimate, computing metrics) is
still fully unit-tested by injecting fakes for the two tool-call boundaries
— see `tests/unit/evaluation/test_legalizer.py`.
"""

import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from modules.evaluation import bookshelf_io, def_io, dreamplace_runner, openroad_runner
from shared.metrics.congestion import compute_congestion_overflow
from shared.metrics.hpwl import compute_hpwl
from shared.metrics.legality import compute_legality_violations
from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.metrics import MetricsObject
from shared.schemas.placement import PlacementJSON


def _run_dreamplace_legalization(graph: CircuitGraph, placement: PlacementJSON, work_dir: Path) -> PlacementJSON:
    """Runs DREAMPlace in legalize + detailed-place-only mode (global
    placement is skipped — Person B's generator already produced one) and
    returns the legalized PlacementJSON. Isolated into its own function so
    `legalize_and_score`'s orchestration can be tested by monkeypatching
    this single call, independent of whether DREAMPlace is installed."""
    aux_path = bookshelf_io.write_bookshelf(graph, placement, work_dir)
    config = dreamplace_runner.build_dreamplace_config(
        aux_path,
        work_dir,
        global_place_flag=0,
        legalize_flag=1,
        detailed_place_flag=1,
        random_seed=placement.generation_metadata.seed,
    )
    config_path = dreamplace_runner.write_config(config, work_dir / f"{graph.design_name}.legalize.json")
    result = dreamplace_runner.run_dreamplace(config_path)
    if result.returncode != 0:
        raise dreamplace_runner.DreamplaceRunError(
            f"DREAMPlace legalization failed (exit {result.returncode}):\n{result.stderr}"
        )
    output_pl = work_dir / f"{graph.design_name}.pl"
    legalized = bookshelf_io.read_bookshelf_placement(
        output_pl,
        design_name=graph.design_name,
        model_variant=placement.generation_metadata.model_variant,
        seed=placement.generation_metadata.seed,
    )
    legalized.generation_metadata.is_legalized = True
    return legalized


def _run_congestion_estimate(
    graph: CircuitGraph, legalized: PlacementJSON, work_dir: Path
) -> Tuple[Dict[tuple, float], Dict[tuple, float]]:
    """See `openroad_runner.py`'s module docstring: blocked on a real tech
    LEF this project has no source for yet. `lef_path` is a placeholder —
    `estimate_congestion` fails before that gap even matters, since
    OpenROAD itself isn't installed in this environment either. That
    failure is correct behavior right now, not something to route around."""
    def_path = def_io.write_def(graph, legalized, work_dir / f"{graph.design_name}.def")
    lef_path = work_dir / f"{graph.design_name}.tech.lef"
    return openroad_runner.estimate_congestion(lef_path, def_path, work_dir)


def legalize_and_score(
    placement: PlacementJSON, graph: CircuitGraph, work_dir: Optional[Path] = None
) -> Tuple[PlacementJSON, MetricsObject]:
    """Input: a Placement JSON with `is_legalized: false`. Output: a
    Placement JSON with `is_legalized: true` (legality violations
    resolved) plus the MetricsObject (Section 3.5)."""
    start = time.perf_counter()

    owns_work_dir = work_dir is None
    work_dir = Path(work_dir) if work_dir is not None else Path(tempfile.mkdtemp(prefix="legalize_and_score_"))
    try:
        legalized = _run_dreamplace_legalization(graph, placement, work_dir)
        routing_demand, routing_capacity = _run_congestion_estimate(graph, legalized, work_dir)

        metrics = MetricsObject(
            hpwl=compute_hpwl(legalized, graph),
            congestion_overflow=compute_congestion_overflow(routing_demand, routing_capacity),
            legality_violations=compute_legality_violations(legalized, graph),
            runtime_seconds=time.perf_counter() - start,
        )
        return legalized, metrics
    finally:
        if owns_work_dir:
            shutil.rmtree(work_dir, ignore_errors=True)
