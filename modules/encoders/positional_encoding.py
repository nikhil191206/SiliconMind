"""Structural positional encodings for DeepGate4 (TECHNICAL.md Section 4.A:
"global + local structural positional encodings").

- Local PE: cheap, per-node structural statistics (degree, incident hyperedge
  count, pin count) — O(N), always computed exactly regardless of chip size.
- Global PE: Laplacian eigenvector positional encoding (Dwivedi et al.),
  top-k eigenvectors of the normalized graph Laplacian. Dense eigendecomposition
  is only tractable up to a few thousand nodes; above that we fall back to a
  sparse Lanczos solver (scipy.sparse.linalg.eigsh), which is standard practice
  for large-graph LapPE but still expensive at full-chip (millions of std
  cells) scale — this is a known scalability limit of exact LapPE noted here,
  not silently hidden, and is exactly the kind of thing the comparative
  encoder benchmark (Section 1.9.3) should measure runtime/memory for.
"""

import numpy as np
import scipy.sparse as sp
import torch
from scipy.sparse.linalg import eigsh

from shared.schemas.circuit_graph import CircuitGraph

LOCAL_PE_DIM = 3
DENSE_EIGH_NODE_LIMIT = 2000


def compute_local_pe(graph: CircuitGraph, edge_index: torch.Tensor) -> torch.Tensor:
    """[num_nodes, LOCAL_PE_DIM]: degree, incident-hyperedge count, log(pin_count+1)."""
    num_nodes = graph.num_nodes
    degree = torch.zeros(num_nodes)
    if edge_index.numel() > 0:
        degree.scatter_add_(0, edge_index[1], torch.ones(edge_index.shape[1]))

    hyperedge_count = torch.zeros(num_nodes)
    for hyperedge in graph.hyperedges:
        members = list(hyperedge.sink_nodes)
        if hyperedge.driver_node is not None:
            members.append(hyperedge.driver_node)
        for node_id in members:
            hyperedge_count[node_id] += 1.0

    log_pins = torch.tensor([float(np.log1p(n.pin_count)) for n in graph.nodes])

    return torch.stack([degree, hyperedge_count, log_pins], dim=1)


def compute_global_pe(graph: CircuitGraph, edge_index: torch.Tensor, k: int = 8) -> torch.Tensor:
    """[num_nodes, k] top-k normalized-Laplacian eigenvectors, zero-padded if
    num_nodes is too small to have k non-trivial eigenvectors."""
    num_nodes = graph.num_nodes
    if num_nodes <= 2:
        return torch.zeros(num_nodes, k)

    k_eff = min(k, num_nodes - 2)

    row, col = edge_index[0].numpy(), edge_index[1].numpy()
    data = np.ones(len(row))
    adjacency = sp.coo_matrix((data, (row, col)), shape=(num_nodes, num_nodes)).tocsr()
    # Collapse any duplicate entries (shouldn't occur from star_expansion, but
    # defensive since duplicate edges would corrupt the degree normalization).
    adjacency.data[:] = 1.0

    degree = np.asarray(adjacency.sum(axis=1)).flatten()
    degree[degree == 0] = 1.0  # isolated nodes: avoid divide-by-zero, contribute 0 eigenvector energy
    d_inv_sqrt = sp.diags(1.0 / np.sqrt(degree))
    laplacian = sp.eye(num_nodes) - d_inv_sqrt @ adjacency @ d_inv_sqrt

    if num_nodes <= DENSE_EIGH_NODE_LIMIT:
        eigenvalues, eigenvectors = np.linalg.eigh(laplacian.toarray())
    else:
        # Smallest-magnitude eigenvectors of a PSD matrix via shift-invert
        # Lanczos — standard approach for large sparse Laplacian PE.
        eigenvalues, eigenvectors = eigsh(laplacian.tocsc(), k=k_eff + 1, sigma=0, which="LM")

    order = np.argsort(eigenvalues)
    # Skip the trivial 0th eigenvector (constant, carries no structural signal).
    selected = eigenvectors[:, order[1 : k_eff + 1]]

    pe = np.zeros((num_nodes, k), dtype=np.float32)
    pe[:, :k_eff] = selected
    return torch.from_numpy(pe)
