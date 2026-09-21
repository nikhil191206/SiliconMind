"""PlacementGenerator — TECHNICAL.md Section 4.B.

Owns the flow-matching/diffusion model, wiring it to Person A's
EncoderOutput as conditioning, and the hard-freezing mechanism (Section
1.7) that makes natural-language editing possible without unintended
drift elsewhere in the layout.

*** Signature note — flag this to the team before merging ***
TECHNICAL.md Section 4.B's literal signature is:

    def generate(self, encoder_output, frozen_placements=None,
                 guidance_terms=None, seed=0) -> PlacementJSON

That signature cannot actually produce a schema-valid PlacementJSON: Section
3.3 requires `design_name`, and turning normalized model output into real
placement coordinates requires the die dimensions — neither is present in
EncoderOutput (Section 3.2 has only embeddings + node_id_order). Legality/
wirelength guidance similarly need real node widths/heights and net
connectivity, which EncoderOutput also doesn't carry.

This is a genuine interface gap, not a stylistic choice. `generate()`
below adds one extra required parameter, `graph: CircuitGraph`, to the
literal signature. See NOTES.md for the two alternative fixes considered
(extend EncoderOutput itself — jointly owned by A and B, so needs A's
sign-off; or pass CircuitGraph here) and why this file picks the latter
as the lower-blast-radius option pending the team's actual review.
"""

from typing import List, Optional

import torch

from modules.generator.base import GenerationStrategy
from modules.generator.flow_matching import FlowMatchingGenerationStrategy
from modules.generator.freeze import build_frozen_mask
from modules.generator.guidance import combined_guidance_fn
from modules.generator.types import FrozenNode, GuidanceConfig
from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.encoder_output import EncoderOutput
from shared.schemas.placement import GenerationMetadata, Orientation, PlacementEntry, PlacementJSON

MODEL_VARIANT = "DE-HNN+DeepGate4_flowmatching_v1"


class GenerationProducedInvalidCoordinatesError(RuntimeError):
    """Raised per TECHNICAL.md Section 7: "Generator produces NaN/invalid
    coordinates: B's generate() must validate its own output before
    returning; on failure, retry once with a new seed, then raise an
    explicit error rather than silently passing invalid data to C." Both
    the retry and this final raise happen in `_sample_with_retry` below."""


class PlacementGenerator:
    def __init__(self, strategy: Optional[GenerationStrategy] = None):
        self.strategy: GenerationStrategy = strategy if strategy is not None else FlowMatchingGenerationStrategy()

    def _sample_with_retry(
        self,
        encoder_output: EncoderOutput,
        num_nodes: int,
        frozen_mask: torch.Tensor,
        frozen_values: torch.Tensor,
        guidance_fn,
        seed: int,
    ) -> torch.Tensor:
        for attempt_seed in (seed, seed + 1):
            rng = torch.Generator().manual_seed(attempt_seed)
            z = self.strategy.sample(
                node_embeddings=encoder_output.node_embeddings,
                global_embedding=encoder_output.global_embedding,
                num_nodes=num_nodes,
                frozen_mask=frozen_mask,
                frozen_values=frozen_values,
                guidance_fn=guidance_fn,
                generator=rng,
            )  # [N,2] normalized ([0,1], die-relative) coordinates
            if torch.isfinite(z).all():
                return z
        raise GenerationProducedInvalidCoordinatesError(
            f"sampling produced NaN/inf coordinates for seeds {seed} and {seed + 1} — "
            "not retried further; this indicates a real bug (e.g. an unbounded guidance "
            "term), not sampling noise, per TECHNICAL.md Section 7."
        )

    def generate(
        self,
        encoder_output: EncoderOutput,
        graph: CircuitGraph,
        frozen_placements: Optional[List[FrozenNode]] = None,
        guidance_terms: Optional[GuidanceConfig] = None,
        seed: int = 0,
    ) -> PlacementJSON:
        """frozen_placements entries are EXCLUDED from the generative
        variable tensor entirely — implemented via index masking before
        and throughout the sampling loop (Section 1.7), and the output for
        those nodes is copied verbatim from `frozen_placements` below
        rather than derived from the model, so it is bit-identical to the
        input by construction, not merely "close"."""
        expected_order = [n.node_id for n in graph.nodes]
        if encoder_output.node_id_order != expected_order:
            raise ValueError(
                "encoder_output.node_id_order must match graph's node_id order exactly (Section 3.2): "
                f"{encoder_output.node_id_order} != {expected_order}"
            )

        num_nodes = len(graph.nodes)
        node_id_to_index = {node_id: i for i, node_id in enumerate(encoder_output.node_id_order)}

        frozen_mask, frozen_values = build_frozen_mask(
            num_nodes, node_id_to_index, graph.die, frozen_placements
        )
        frozen_by_id = {fp.node_id: fp for fp in (frozen_placements or [])}

        guidance_fn = None
        if guidance_terms is not None:
            guidance_fn = combined_guidance_fn(graph, guidance_terms, node_id_to_index)

        z = self._sample_with_retry(encoder_output, num_nodes, frozen_mask, frozen_values, guidance_fn, seed)

        placements = []
        for node_id, idx in node_id_to_index.items():
            if node_id in frozen_by_id:
                # Bypass z / normalization entirely for frozen nodes: copy
                # the given entry's x, y, orientation verbatim. Round-
                # tripping through (x / die.width) * die.width is not
                # guaranteed bit-identical in IEEE754, so the freeze
                # guarantee must not depend on that arithmetic at all.
                original = frozen_by_id[node_id]
                placements.append(
                    PlacementEntry(node_id=node_id, x=original.x, y=original.y, orientation=original.orientation)
                )
                continue

            x_norm = min(max(z[idx, 0].item(), 0.0), 1.0)
            y_norm = min(max(z[idx, 1].item(), 0.0), 1.0)
            placements.append(
                PlacementEntry(
                    node_id=node_id,
                    x=x_norm * graph.die.width,
                    y=y_norm * graph.die.height,
                    orientation=Orientation.N,
                )
            )

        return PlacementJSON(
            design_name=graph.design_name,
            placements=placements,
            generation_metadata=GenerationMetadata(model_variant=MODEL_VARIANT, seed=seed, is_legalized=False),
        )
