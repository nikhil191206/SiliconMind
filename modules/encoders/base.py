"""NetlistEncoder abstract interface — TECHNICAL.md Section 4.A.

Every concrete encoder (gcn.py, gat.py, de_hnn.py, deepgate4.py) implements
this exact interface so the comparative benchmark (Section 1.5, 1.9.3) can
swap encoders without touching any downstream code, and so Person B's
generator sees an identical EncoderOutput schema regardless of which
encoder produced it.
"""

from abc import ABC, abstractmethod

from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.encoder_output import EncoderOutput


class NetlistEncoder(ABC):
    @abstractmethod
    def encode(self, graph: CircuitGraph) -> EncoderOutput:
        """Returns node_embeddings [N, D_node] and global_embedding [D_global],
        per the schema in Section 3.2. Must not mutate the input graph."""
        raise NotImplementedError
