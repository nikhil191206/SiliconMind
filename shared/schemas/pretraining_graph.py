"""Pretraining Graph — a deliberately SEPARATE schema from CircuitGraph
(Section 3.1), for CircuitNet-sourced encoder pretraining data only
(TECHNICAL.md Section 1.14.2).

Why this isn't just CircuitGraph: CircuitNode requires width>0 and
height>0 (real physical geometry). CircuitNet 3.0's real, official public
release does not include LEF/DEF/layout data -- confirmed directly against
the dataset's own HuggingFace page (huggingface.co/datasets/SKLP-EDA-LAB/
CircuitNet3.0), which states layout artifacts "are not yet available."
Inventing placeholder width/height to force real CircuitNet data through
the CircuitGraph schema would be fabricating data, which this project does
not do. What CircuitNet genuinely provides instead: real structural
netlist connectivity (from final_netlist.v) and real per-instance timing
data (from feature.json) -- this schema carries exactly that, and nothing
invented.

This schema is consumed ONLY by the encoder pretraining path
(experiments/pretrain_encoder_circuitnet.py) and is never substituted for
a real CircuitGraph anywhere in the main pipeline (encoders trained on
this data are fine-tuned afterward on real CircuitGraph data from ISPD02/
ISPD2015/Ariane, which do have real geometry).
"""

from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class PretrainingNode(BaseModel):
    node_id: int = Field(..., ge=0)
    cell_name: str = Field(..., description="real standard-cell type name, e.g. 'DFFHQX1', 'AND2X1'")
    pin_count: int = Field(..., ge=1)
    is_sequential: bool = Field(..., description="True for real flip-flop/latch cells (has a clock pin)")

    # Real per-instance timing/electrical features from feature.json,
    # usable as pretraining INPUT features (never leak `slack`/`AT`, the
    # pretraining targets, into these).
    drive_strength: Optional[float] = None
    fanout_load: Optional[float] = None
    fanout_res: Optional[float] = None

    # Real pretraining regression targets.
    slack: Optional[float] = Field(None, description="real timing slack from the actual STA report")
    arrival_time: Optional[float] = Field(None, description="real arrival time (AT) from the actual STA report")


class PretrainingHyperedge(BaseModel):
    net_id: int = Field(..., ge=0)
    driver_node: Optional[int] = Field(None, description="node_id of the real driving pin's instance, or null for a primary input port")
    sink_nodes: List[int]


class PretrainingGraph(BaseModel):
    design_name: str
    nodes: List[PretrainingNode]
    hyperedges: List[PretrainingHyperedge]

    @model_validator(mode="after")
    def _check_contiguous_and_referenced_ids(self) -> "PretrainingGraph":
        node_ids = [n.node_id for n in self.nodes]
        if node_ids != list(range(len(node_ids))):
            raise ValueError("node_id must be 0-indexed and contiguous")
        valid_ids = set(node_ids)
        for h in self.hyperedges:
            if h.driver_node is not None and h.driver_node not in valid_ids:
                raise ValueError(f"hyperedge {h.net_id}: driver_node {h.driver_node} not a valid node_id")
            for sink in h.sink_nodes:
                if sink not in valid_ids:
                    raise ValueError(f"hyperedge {h.net_id}: sink_node {sink} not a valid node_id")
        return self

    @property
    def num_nodes(self) -> int:
        return len(self.nodes)

    @property
    def num_hyperedges(self) -> int:
        return len(self.hyperedges)
