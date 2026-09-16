from shared.metrics.geometry import effective_dims, node_bbox, node_center
from shared.schemas.placement import Orientation


def test_effective_dims_unrotated_orientations_keep_width_height():
    for orientation in (Orientation.N, Orientation.S, Orientation.FN, Orientation.FS):
        assert effective_dims(10.0, 4.0, orientation) == (10.0, 4.0)


def test_effective_dims_rotated_orientations_swap_width_height():
    for orientation in (Orientation.E, Orientation.W, Orientation.FE, Orientation.FW):
        assert effective_dims(10.0, 4.0, orientation) == (4.0, 10.0)


def test_node_bbox_treats_xy_as_lower_left_corner():
    assert node_bbox(x=5.0, y=3.0, width=2.0, height=4.0, orientation=Orientation.N) == (5.0, 3.0, 7.0, 7.0)


def test_node_bbox_rotated_swaps_extent_not_origin():
    assert node_bbox(x=5.0, y=3.0, width=2.0, height=4.0, orientation=Orientation.E) == (5.0, 3.0, 9.0, 5.0)


def test_node_center_matches_bbox_midpoint():
    cx, cy = node_center(x=0.0, y=0.0, width=2.0, height=4.0, orientation=Orientation.N)
    assert (cx, cy) == (1.0, 2.0)
