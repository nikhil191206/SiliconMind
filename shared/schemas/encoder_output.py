"""Encoder Output -> Generator Input — TECHNICAL.md Section 3.2.

Owned jointly by Person A and Person B — changes require both to sign off,
logged in shared/schemas/CHANGELOG.md.

Default dimensionalities, frozen once encoder training starts: D_NODE=256,
D_GLOBAL=512. Changing these after B has started training breaks B's model
input layer.
"""

from typing import List

import torch
from pydantic import BaseModel, ConfigDict, field_validator

D_NODE = 256
D_GLOBAL = 512


class EncoderOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    node_embeddings: torch.Tensor
    global_embedding: torch.Tensor
    node_id_order: List[int]

    @field_validator("node_embeddings")
    @classmethod
    def _check_node_embeddings_shape(cls, v: torch.Tensor) -> torch.Tensor:
        if v.ndim != 2 or v.shape[1] != D_NODE:
            raise ValueError(f"node_embeddings must have shape [num_nodes, {D_NODE}], got {tuple(v.shape)}")
        return v

    @field_validator("global_embedding")
    @classmethod
    def _check_global_embedding_shape(cls, v: torch.Tensor) -> torch.Tensor:
        if v.ndim != 1 or v.shape[0] != D_GLOBAL:
            raise ValueError(f"global_embedding must have shape [{D_GLOBAL}], got {tuple(v.shape)}")
        return v

    def model_post_init(self, __context) -> None:
        if self.node_embeddings.shape[0] != len(self.node_id_order):
            raise ValueError(
                "node_embeddings row count must match len(node_id_order): "
                f"{self.node_embeddings.shape[0]} != {len(self.node_id_order)}"
            )
