from pathlib import Path

import pytest
import torch

from modules.encoders.pretraining_model import (
    UNKNOWN_CELL_TOKEN,
    PretrainingGCN,
    build_cell_vocabulary,
    pretraining_inputs,
    pretraining_star_expansion_edge_index,
)
from modules.intake.parsers.circuitnet_parser import parse_circuitnet_design

DESIGN_DIR = Path("data/raw/circuitnet/circuitNetv3/dataset/Final/0_jt12_amp")

pytestmark = pytest.mark.skipif(
    not DESIGN_DIR.exists(), reason="real CircuitNet data not present in data/raw/ — see data/README.md"
)


@pytest.fixture(scope="module")
def real_graph():
    graph, _ = parse_circuitnet_design(DESIGN_DIR)
    return graph


def test_build_cell_vocabulary_includes_unknown_token_and_real_cells(real_graph):
    vocab = build_cell_vocabulary([real_graph])
    assert vocab[UNKNOWN_CELL_TOKEN] == 0
    assert "BUFX12" in vocab
    assert len(vocab) == 1 + len({n.cell_name for n in real_graph.nodes})


def test_pretraining_inputs_shapes_and_mask(real_graph):
    vocab = build_cell_vocabulary([real_graph])
    cell_ids, scalars, targets, mask = pretraining_inputs(real_graph, vocab)

    n = real_graph.num_nodes
    assert cell_ids.shape == (n,)
    assert scalars.shape == (n, 4)
    assert targets.shape == (n,)
    assert mask.shape == (n,)
    assert mask.sum().item() == sum(1 for node in real_graph.nodes if node.slack is not None)


def test_pretraining_inputs_maps_unseen_cell_to_unknown_token(real_graph):
    empty_vocab = {UNKNOWN_CELL_TOKEN: 0}  # simulates a cell type never seen in train_chips
    cell_ids, _, _, _ = pretraining_inputs(real_graph, empty_vocab)
    assert (cell_ids == 0).all()


def test_pretraining_star_expansion_matches_hyperedge_count(real_graph):
    edge_index = pretraining_star_expansion_edge_index(real_graph)
    num_driven_hyperedges = sum(1 for h in real_graph.hyperedges if h.driver_node is not None)
    num_sink_endpoints = sum(len(h.sink_nodes) for h in real_graph.hyperedges if h.driver_node is not None)
    assert edge_index.shape == (2, 2 * num_sink_endpoints)
    assert num_driven_hyperedges <= real_graph.num_hyperedges


def test_masked_mse_loss_is_none_when_no_labels_present(real_graph):
    vocab = build_cell_vocabulary([real_graph])
    model = PretrainingGCN(vocab_size=len(vocab))
    cell_ids, scalars, targets, _ = pretraining_inputs(real_graph, vocab)
    edge_index = pretraining_star_expansion_edge_index(real_graph)
    all_false_mask = torch.zeros(real_graph.num_nodes, dtype=torch.bool)

    loss = model.masked_mse_loss(cell_ids, scalars, edge_index, targets, all_false_mask)
    assert loss is None


def test_training_loss_decreases_on_a_real_overfit_example(real_graph):
    vocab = build_cell_vocabulary([real_graph])
    model = PretrainingGCN(vocab_size=len(vocab))
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-2)
    cell_ids, scalars, targets, mask = pretraining_inputs(real_graph, vocab)
    edge_index = pretraining_star_expansion_edge_index(real_graph)

    losses = []
    for _ in range(30):
        loss = model.masked_mse_loss(cell_ids, scalars, edge_index, targets, mask)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        losses.append(loss.item())

    assert losses[-1] < losses[0]
