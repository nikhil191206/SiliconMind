from shared.metrics.congestion import compute_congestion_overflow


def test_congestion_overflow_hand_computed():
    demand = {(0, 0): 5.0, (0, 1): 2.0, (1, 0): 10.0}
    capacity = {(0, 0): 3.0, (0, 1): 5.0, (1, 0): 10.0}
    # max(0,5-3) + max(0,2-5) + max(0,10-10) = 2 + 0 + 0 = 2
    assert compute_congestion_overflow(demand, capacity) == 2.0


def test_congestion_overflow_missing_capacity_treated_as_zero():
    demand = {(2, 2): 4.0}
    capacity: dict = {}
    assert compute_congestion_overflow(demand, capacity) == 4.0


def test_congestion_overflow_missing_demand_treated_as_zero_never_negative():
    demand: dict = {}
    capacity = {(3, 3): 7.0}
    assert compute_congestion_overflow(demand, capacity) == 0.0


def test_congestion_overflow_zero_when_capacity_meets_demand_everywhere():
    demand = {(0, 0): 3.0, (0, 1): 1.0}
    capacity = {(0, 0): 3.0, (0, 1): 5.0}
    assert compute_congestion_overflow(demand, capacity) == 0.0
