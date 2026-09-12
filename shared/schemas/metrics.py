"""Verification Contract metrics object — TECHNICAL.md Section 3.5.

Owned by Person C. No module other than C's evaluation code may compute
these three values independently — every reported number in the project
must trace back to shared/metrics/ (Section 1.4).
"""

from pydantic import BaseModel, Field


class MetricsObject(BaseModel):
    hpwl: float = Field(..., ge=0.0)
    congestion_overflow: float = Field(..., ge=0.0)
    legality_violations: int = Field(..., ge=0, description="must be 0 in final output")
    runtime_seconds: float = Field(..., ge=0.0)
