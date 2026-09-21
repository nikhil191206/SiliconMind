"""Walks data/raw/, parses every real design it recognizes with the
appropriate real parser, and caches the result as Circuit Graph JSON
(TECHNICAL.md Section 3.1) under data/processed/<source>/<design>.json.

INSTRUCTIONS.md Section 3: "a single script that, once run, walks
data/raw/, calls the appropriate parser per source, and populates
data/processed/ with cached CircuitGraph JSON files." This cache is
derived data, never hand-edited, never committed (data/processed/ is
gitignored) — delete and re-run this script if it's ever out of sync with
data/raw/.

Usage:
    python -m data.processed.build_cache [--source ispd02] [--source ispd2015] [--source ariane_circuit_training]

With no --source, processes every recognized source found in data/raw/.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Iterator, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, for `python data/processed/build_cache.py`

from modules.intake.parsers.lefdef_parser import lefdef_to_circuit_graph  # noqa: E402
from modules.intake.parsers.protobuf_parser import parse_protobuf_netlist  # noqa: E402
from shared.schemas.circuit_graph import CircuitGraph  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = REPO_ROOT / "data" / "raw"
DATA_PROCESSED = REPO_ROOT / "data" / "processed"


def _iter_ispd02_designs() -> Iterator[Tuple[str, Path, Path]]:
    base = DATA_RAW / "ispd02" / "ibmISPD02Bench_LEFDEF"
    if not base.is_dir():
        return
    for design_dir in sorted(base.iterdir()):
        if not design_dir.is_dir():
            continue
        name = design_dir.name
        lef, deff = design_dir / f"{name}.lef", design_dir / f"{name}.def"
        if lef.exists() and deff.exists():
            yield name, lef, deff


def _iter_ariane_circuit_training() -> Iterator[Tuple[str, Path]]:
    pb = DATA_RAW / "ariane_circuit_training" / "netlist.pb.txt"
    if pb.exists():
        yield "ariane", pb


def _iter_ispd2015_designs() -> Iterator[Tuple[str, list, Path]]:
    base = DATA_RAW / "ispd2015" / "ispd_2015_contest_benchmark"
    if not base.is_dir():
        return
    for design_dir in sorted(base.iterdir()):
        if not design_dir.is_dir():
            continue
        name = design_dir.name
        tech, cells, floorplan = design_dir / "tech.lef", design_dir / "cells.lef", design_dir / "floorplan.def"
        if tech.exists() and cells.exists() and floorplan.exists():
            yield name, [tech, cells], floorplan


def build_ispd02_cache() -> int:
    out_dir = DATA_PROCESSED / "ispd02"
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for name, lef, deff in _iter_ispd02_designs():
        t0 = time.time()
        graph = lefdef_to_circuit_graph(lef, deff)
        _write_graph(graph, out_dir / f"{name}.json")
        print(f"[ispd02] {name}: {graph.num_nodes} nodes, {graph.num_hyperedges} hyperedges ({time.time()-t0:.2f}s)")
        count += 1
    return count


def build_ariane_circuit_training_cache() -> int:
    out_dir = DATA_PROCESSED / "ariane_circuit_training"
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for name, pb in _iter_ariane_circuit_training():
        t0 = time.time()
        graph = parse_protobuf_netlist(pb, design_name=name)
        _write_graph(graph, out_dir / f"{name}.json")
        print(f"[ariane_circuit_training] {name}: {graph.num_nodes} nodes, {graph.num_hyperedges} hyperedges ({time.time()-t0:.2f}s)")
        count += 1
    return count


def build_ispd2015_cache() -> int:
    out_dir = DATA_PROCESSED / "ispd2015"
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for name, lef_paths, floorplan in _iter_ispd2015_designs():
        t0 = time.time()
        graph = lefdef_to_circuit_graph(lef_paths, floorplan)
        _write_graph(graph, out_dir / f"{name}.json")
        print(f"[ispd2015] {name}: {graph.num_nodes} nodes, {graph.num_hyperedges} hyperedges ({time.time()-t0:.2f}s)")
        count += 1
    return count


def _write_graph(graph: CircuitGraph, path: Path) -> None:
    path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")


SOURCE_BUILDERS = {
    "ispd02": build_ispd02_cache,
    "ispd2015": build_ispd2015_cache,
    "ariane_circuit_training": build_ariane_circuit_training_cache,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", choices=sorted(SOURCE_BUILDERS), default=None)
    args = parser.parse_args()

    sources = args.source or sorted(SOURCE_BUILDERS)
    total = 0
    for source in sources:
        total += SOURCE_BUILDERS[source]()

    if total == 0:
        print(
            "No real designs found to cache. Check data/raw/ against data/README.md's checklist "
            "— this script never substitutes placeholder data."
        )
    else:
        print(f"Cached {total} real design(s) under {DATA_PROCESSED}")


if __name__ == "__main__":
    main()
