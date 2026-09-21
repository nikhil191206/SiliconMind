"""FastAPI Backend Application — TECHNICAL.md Section 1.2 / Section 8.

Integrates intake, netlist encoding, placement generation, natural-language editing,
verification, and diff reporting into unified APIs.

Every placement this API hands back has been through `legalize_and_score`
(Person C) before it's returned — TECHNICAL.md Section 1.8 says the
visualizer "reads only the verified Placement JSON," and the only way to
guarantee that from here is to never emit an unverified one. DREAMPlace/
OpenROAD are not installed in this dev environment (see
modules/evaluation/NOTES.md), so verification is best-effort: `_legalize`
below catches exactly the documented `*NotInstalledError`/`*RunError` types
and reports `verification_status="unavailable: ..."` rather than either (a)
crashing the whole request, which would make the API unusable until the
tools are installed, or (b) silently pretending an unlegalized placement is
final, which is exactly the failure mode Section 1.8 exists to prevent. A
caller can and should tell the difference by checking `verification_status`.
"""

import tempfile
from pathlib import Path
from typing import Optional, Tuple

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from modules.encoders.de_hnn import DEHNNEncoder
from modules.evaluation.dreamplace_runner import DreamplaceNotInstalledError, DreamplaceRunError
from modules.evaluation.legalizer import legalize_and_score
from modules.evaluation.openroad_runner import OpenroadNotInstalledError, OpenroadRunError
from modules.generator.freeze import ConstraintRequiresClarificationError, constraint_to_generation_inputs
from modules.generator.generator import GenerationProducedInvalidCoordinatesError, PlacementGenerator
from modules.intake.llm_rtl import LLMConfigurationError, synthesize_from_description
from modules.intake.yosys_synthesis import YosysNotInstalledError, YosysSynthesisError, parse_yosys_json, run_yosys_synthesis
from modules.llm_interaction.constraint_parser import parse_constraint
from modules.llm_interaction.diff_report import format_diff_summary, generate_diff_report
from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.constraint import ConstraintObject
from shared.schemas.diff_report import DiffReport
from shared.schemas.metrics import MetricsObject
from shared.schemas.placement import PlacementJSON

_VERIFICATION_UNAVAILABLE_ERRORS = (
    DreamplaceNotInstalledError,
    DreamplaceRunError,
    OpenroadNotInstalledError,
    OpenroadRunError,
)


def _legalize(placement: PlacementJSON, graph: CircuitGraph) -> Tuple[PlacementJSON, Optional[MetricsObject], str]:
    """Best-effort call into Person C's legalize_and_score. Returns
    (placement, metrics, verification_status) — placement is the legalized
    one on success, or the original (still is_legalized=False) placement
    unchanged if verification is unavailable, so a caller always gets a
    schema-valid PlacementJSON either way, honestly labeled."""
    try:
        legalized, metrics = legalize_and_score(placement, graph)
        return legalized, metrics, "verified"
    except _VERIFICATION_UNAVAILABLE_ERRORS as exc:
        return placement, None, f"unavailable: {exc}"

app = FastAPI(
    title="SiliconMind — AI-Driven Chip Placement API",
    description="End-to-end backend API supporting beginner RTL intake, placement generation, natural-language editing, and diff reporting.",
    version="1.0.0",
)


# API Request / Response Schemas
class DraftRTLRequest(BaseModel):
    description: str
    template: Optional[str] = None
    api_key: Optional[str] = None


class DraftRTLResponse(BaseModel):
    rtl_code: str


class SynthesizeRTLRequest(BaseModel):
    rtl_code: Optional[str] = None
    rtl_path: Optional[str] = None
    yosys_json_data: Optional[str] = None
    design_name: Optional[str] = "beginner_design"


class GeneratePlacementRequest(BaseModel):
    graph: CircuitGraph
    seed: int = 0


class GeneratePlacementResponse(BaseModel):
    placement: PlacementJSON
    metrics: Optional[MetricsObject] = None
    verification_status: str


class EditPlacementRequest(BaseModel):
    graph: CircuitGraph
    previous_placement: PlacementJSON
    instruction: str
    seed: int = 0
    api_key: Optional[str] = None


class EditPlacementResponse(BaseModel):
    requires_clarification: bool
    clarification_message: Optional[str] = None
    constraint: Optional[ConstraintObject] = None
    new_placement: Optional[PlacementJSON] = None
    metrics_before: Optional[MetricsObject] = None
    metrics_after: Optional[MetricsObject] = None
    verification_status: Optional[str] = None
    diff_report: Optional[DiffReport] = None
    diff_summary: Optional[str] = None


class DiffRequest(BaseModel):
    before_placement: PlacementJSON
    after_placement: PlacementJSON
    constraint: ConstraintObject
    metrics_before: Optional[MetricsObject] = None
    metrics_after: Optional[MetricsObject] = None


@app.get("/health")
def health_check():
    return {"status": "ok", "app": "SiliconMind Placement Backend"}


@app.post("/api/intake/draft-rtl", response_model=DraftRTLResponse)
def draft_rtl(req: DraftRTLRequest):
    """Drafts synthesizable Verilog RTL from natural-language design description."""
    try:
        rtl = synthesize_from_description(req.description, template=req.template, api_key=req.api_key)
        return DraftRTLResponse(rtl_code=rtl)
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@app.post("/api/intake/synthesize", response_model=CircuitGraph)
def synthesize_rtl(req: SynthesizeRTLRequest):
    """Synthesizes Verilog RTL using Yosys or parses Yosys netlist JSON into CircuitGraph."""
    if req.yosys_json_data:
        try:
            return parse_yosys_json(req.yosys_json_data, design_name=req.design_name)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to parse Yosys JSON: {exc}")

    if not req.rtl_code and not req.rtl_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Must provide rtl_code, rtl_path, or yosys_json_data.")

    # Write rtl_code to temp file if provided directly
    temp_file = None
    rtl_file_path = req.rtl_path

    if req.rtl_code:
        temp_file = tempfile.NamedTemporaryFile("w", suffix=".v", delete=False)
        temp_file.write(req.rtl_code)
        temp_file.close()
        rtl_file_path = temp_file.name

    try:
        graph = run_yosys_synthesis(rtl_file_path, top_module=req.design_name)
        return graph
    except YosysNotInstalledError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except YosysSynthesisError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    finally:
        if temp_file and Path(temp_file.name).exists():
            Path(temp_file.name).unlink()


@app.post("/api/placement/generate", response_model=GeneratePlacementResponse)
def generate_placement(req: GeneratePlacementRequest):
    """Encodes CircuitGraph using Person A's encoder, generates a layout using
    Person B's flow-matching generator, then runs it through Person C's
    legalizer before returning — see this module's docstring for why."""
    try:
        encoder = DEHNNEncoder()
        encoder_output = encoder.encode(req.graph)

        generator = PlacementGenerator()
        placement = generator.generate(encoder_output=encoder_output, graph=req.graph, seed=req.seed)
    except GenerationProducedInvalidCoordinatesError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Placement generation failed: {exc}")

    placement, metrics, verification_status = _legalize(placement, req.graph)
    return GeneratePlacementResponse(placement=placement, metrics=metrics, verification_status=verification_status)


@app.post("/api/placement/edit", response_model=EditPlacementResponse)
def edit_placement(req: EditPlacementRequest):
    """Processes natural-language edit instruction, parses constraint, regenerates affected region, and returns diff report."""
    constraint = parse_constraint(req.instruction, req.previous_placement, graph=req.graph, api_key=req.api_key)

    if constraint.requires_clarification():
        return EditPlacementResponse(
            requires_clarification=True,
            clarification_message=(
                f"Instruction '{req.instruction}' was ambiguous or low confidence ({constraint.confidence:.2f}). "
                "Please specify target macro names or direction explicitly (e.g. 'Move SRAM_0 away from left edge')."
            ),
            constraint=constraint,
        )

    try:
        frozen_placements, guidance = constraint_to_generation_inputs(constraint, req.previous_placement, graph=req.graph)

        encoder = DEHNNEncoder()
        encoder_output = encoder.encode(req.graph)

        generator = PlacementGenerator()
        new_placement = generator.generate(
            encoder_output=encoder_output,
            graph=req.graph,
            frozen_placements=frozen_placements,
            guidance_terms=guidance,
            seed=req.seed,
        )

        # Legalize BOTH sides so the diff's hpwl_delta/congestion_delta
        # (Section 3.6) are real numbers whenever verification is available,
        # not silently-zero placeholders — see this module's docstring.
        legalized_before, metrics_before, before_status = _legalize(req.previous_placement, req.graph)
        legalized_after, metrics_after, after_status = _legalize(new_placement, req.graph)
        verification_status = after_status if after_status == before_status else f"before: {before_status}; after: {after_status}"

        diff = generate_diff_report(
            legalized_before, legalized_after, constraint, metrics_before=metrics_before, metrics_after=metrics_after
        )
        summary = format_diff_summary(diff, constraint)

        return EditPlacementResponse(
            requires_clarification=False,
            constraint=constraint,
            new_placement=legalized_after,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            verification_status=verification_status,
            diff_report=diff,
            diff_summary=summary,
        )

    except ConstraintRequiresClarificationError as exc:
        return EditPlacementResponse(
            requires_clarification=True,
            clarification_message=str(exc),
            constraint=constraint,
        )
    except GenerationProducedInvalidCoordinatesError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Placement edit failed: {exc}")


@app.post("/api/placement/diff", response_model=DiffReport)
def calculate_diff(req: DiffRequest):
    """Calculates displacement and unexpected moves between two placements given a triggering constraint."""
    return generate_diff_report(
        req.before_placement,
        req.after_placement,
        req.constraint,
        metrics_before=req.metrics_before,
        metrics_after=req.metrics_after,
    )
