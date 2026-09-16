"""Shared geometry helpers backing Section 1.4's formulas.

Neither Circuit Graph JSON (Section 3.1) nor Placement JSON (Section 3.3)
states how `orientation` affects a node's bounding box, or whether (x, y)
is a corner or a center. This module fixes both conventions in one place so
`hpwl.py` and `legality.py` never disagree with each other:

- `(x, y)` is the node's bounding-box origin (lower-left corner) — the same
  convention `shared/mocks/mock_placement.py`'s grid layout already uses,
  and the one Bookshelf `.pl` files use (`modules/evaluation/bookshelf_io.py`).
- `N`/`S`/`FN`/`FS` are 0-degree orientations: width/height as authored.
  `E`/`W`/`FE`/`FW` are 90-degree rotations: effective width/height swap.
  This is the standard LEF/DEF/Bookshelf orientation convention.
"""

from shared.schemas.placement import Orientation

_ROTATED_90 = {Orientation.E, Orientation.W, Orientation.FE, Orientation.FW}


def effective_dims(width: float, height: float, orientation: Orientation) -> tuple[float, float]:
    """Width/height after applying orientation's rotation (not reflection —
    reflection alone, i.e. F-prefixed vs. not, does not change the bounding
    box size)."""
    if orientation in _ROTATED_90:
        return height, width
    return width, height


def node_bbox(
    x: float, y: float, width: float, height: float, orientation: Orientation
) -> tuple[float, float, float, float]:
    """Axis-aligned bounding box as (x_min, y_min, x_max, y_max)."""
    eff_w, eff_h = effective_dims(width, height, orientation)
    return x, y, x + eff_w, y + eff_h


def node_center(
    x: float, y: float, width: float, height: float, orientation: Orientation
) -> tuple[float, float]:
    x_min, y_min, x_max, y_max = node_bbox(x, y, width, height, orientation)
    return (x_min + x_max) / 2.0, (y_min + y_max) / 2.0
