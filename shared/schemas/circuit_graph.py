"""Circuit Graph JSON — TECHNICAL.md Section 3.1.

Owned by Person A. Produced by the intake parser (Person D), consumed by A's
encoders. This is the ONLY format encoder code may accept as input — encoder
code must never parse Verilog/LEF-DEF/Bookshelf/Protobuf directly.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class NodeType(str, Enum):
    MACRO = "MACRO"
    STD_CELL = "STD_CELL"


class CircuitNode(BaseModel):
    node_id: int = Field(..., ge=0, description="0-indexed, contiguous")
    type: NodeType
    width: float = Field(..., gt=0, description="die units")
    height: float = Field(..., gt=0, description="die units")
    pin_count: int = Field(..., ge=0)


class CircuitHyperedge(BaseModel):
    net_id: int = Field(..., ge=0, description="0-indexed, contiguous")
    driver_node: Optional[int] = Field(
        None, description="node_id of the driving pin's node, or null if primary input"
    )
    sink_nodes: List[int] = Field(..., description="node_id list of all sink pins' nodes")


class Die(BaseModel):
    width: float = Field(..., gt=0)
    height: float = Field(..., gt=0)


class CircuitGraph(BaseModel):
    design_name: str
    nodes: List[CircuitNode]
    hyperedges: List[CircuitHyperedge]
    die: Die

    @model_validator(mode="after")
    def _check_contiguous_and_referenced_ids(self) -> "CircuitGraph":
        node_ids = [n.node_id for n in self.nodes]
        if node_ids != list(range(len(node_ids))):
            raise ValueError("node_id must be 0-indexed and contiguous")

        net_ids = [h.net_id for h in self.hyperedges]
        if net_ids != list(range(len(net_ids))):
            raise ValueError("net_id must be 0-indexed and contiguous")

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
