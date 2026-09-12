"""Pass-through legalizer matching legalize_and_score's signature (Section 3.5).

Only checks Placement JSON shape and returns is_legalized=True with placeholder
metrics, so Person B can test freeze-mask logic before Person C's real
DREAMPlace/OpenROAD integration exists. Never a source of reportable numbers.
"""

from shared.schemas.metrics import MetricsObject
from shared.schemas.placement import PlacementJSON


def mock_legalize_and_score(placement: PlacementJSON) -> tuple[PlacementJSON, MetricsObject]:
    legalized = placement.model_copy(deep=True)
    legalized.generation_metadata.is_legalized = True
    metrics = MetricsObject(
        hpwl=0.0,
        congestion_overflow=0.0,
        legality_violations=0,
        runtime_seconds=0.0,
    )
    return legalized, metrics
