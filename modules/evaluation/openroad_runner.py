"""Subprocess wiring to OpenROAD's global-router congestion estimate —
TECHNICAL.md Section 1.4 ("routing_demand and routing_capacity are computed
by DREAMPlace/OpenROAD's global router estimate").

*** Known, flagged gap — see NOTES.md before relying on this in a real run ***
A real global-route congestion estimate needs a technology LEF (routing
layer count, track pitch, via rules) in addition to the design DEF. Circuit
Graph JSON (Section 3.1) carries none of that — it has no routing-layer or
technology information at all, only per-node width/height/pin_count. A real
tech LEF is expected to come from a real PDK (Section 1.13 source 3, ASAP7,
owned on the intake side), not from anything this module can synthesize.
Until a real design is run through a real PDK, `estimate_congestion` below
is wired but genuinely blocked (INSTRUCTIONS.md Section 2's "do not
approximate around it" — a fabricated tech LEF would make every downstream
congestion number meaningless, not just approximate).
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple


class OpenroadNotInstalledError(RuntimeError):
    pass


class OpenroadRunError(RuntimeError):
    pass


def find_openroad_binary() -> str:
    """`OPENROAD_BIN` (documented in environment_setup.md) takes precedence
    so a from-source build in a nonstandard location still works; otherwise
    falls back to whatever `openroad` resolves to on PATH."""
    override = os.environ.get("OPENROAD_BIN")
    if override:
        if not shutil.which(override) and not Path(override).is_file():
            raise OpenroadNotInstalledError(f"OPENROAD_BIN is set to {override!r} but that binary was not found.")
        return override

    found = shutil.which("openroad")
    if not found:
        raise OpenroadNotInstalledError(
            "openroad was not found on PATH and OPENROAD_BIN is not set. "
            "See environment_setup.md's OpenROAD section for install instructions."
        )
    return found


def build_congestion_script(lef_path: Path, def_path: Path, report_path: Path) -> str:
    """Generates the Tcl script `estimate_congestion` feeds to `openroad
    -exit`. Kept as a standalone, pure function (no subprocess call) so its
    generated content is unit-testable without OpenROAD installed."""
    return (
        f'read_lef "{lef_path}"\n'
        f'read_def "{def_path}"\n'
        "global_route\n"
        f'report_congestion > "{report_path}"\n'
        "exit\n"
    )


def _parse_congestion_report(report_text: str) -> Tuple[Dict[tuple, float], Dict[tuple, float]]:
    """Parses OpenROAD's `report_congestion` output (one line per
    over-capacity GCell: `GCell (<x>, <y>) ... demand: <d> capacity: <c>`)
    into the `routing_demand`/`routing_capacity` maps `shared/metrics/
    congestion.py` expects. Unverified against real OpenROAD output — its
    exact report format should be confirmed the first time this actually
    runs (see NOTES.md); this parser is deliberately permissive (skips any
    line it doesn't recognize) rather than guessing at a rigid format."""
    demand: Dict[tuple, float] = {}
    capacity: Dict[tuple, float] = {}
    for line in report_text.splitlines():
        if "demand:" not in line or "capacity:" not in line:
            continue
        try:
            coords_part = line.split("(", 1)[1].split(")", 1)[0]
            x_str, y_str = (p.strip() for p in coords_part.split(","))
            cell = (int(float(x_str)), int(float(y_str)))
            demand_val = float(line.split("demand:", 1)[1].split()[0])
            capacity_val = float(line.split("capacity:", 1)[1].split()[0])
        except (IndexError, ValueError):
            continue
        demand[cell] = demand_val
        capacity[cell] = capacity_val
    return demand, capacity


def estimate_congestion(
    lef_path: Path, def_path: Path, work_dir: Path, openroad_bin: Optional[str] = None
) -> Tuple[Dict[tuple, float], Dict[tuple, float]]:
    """Blocked until a real tech LEF is available (see module docstring) —
    raises `OpenroadNotInstalledError` today via `find_openroad_binary`
    even before reaching that gap, since OpenROAD itself isn't installed
    in this environment either."""
    if openroad_bin is None:
        openroad_bin = find_openroad_binary()

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    report_path = work_dir / "congestion_report.txt"
    script_path = work_dir / "congestion.tcl"
    script_path.write_text(build_congestion_script(lef_path, def_path, report_path))

    result = subprocess.run([openroad_bin, "-exit", str(script_path)], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise OpenroadRunError(f"OpenROAD congestion estimate failed (exit {result.returncode}):\n{result.stderr}")

    return _parse_congestion_report(report_path.read_text())
