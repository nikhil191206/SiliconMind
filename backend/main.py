"""FastAPI Backend Application — TECHNICAL.md Section 1.2 / Section 8.

Integrates intake, netlist encoding, placement generation, natural-language editing,
verification, and diff reporting into unified APIs.
"""

from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from modules.encoders.de_hnn import DEHNNEncoder
from modules.generator.freeze import ConstraintRequiresClarificationError, constraint_to_generation_inputs
from modules.generator.generator import PlacementGenerator
from modules.intake.llm_rtl import LLMConfigurationError, synthesize_from_description
from modules.intake.yosys_synthesis import YosysNotInstalledError, YosysSynthesisError, parse_yosys_json, run_yosys_synthesis
from modules.llm_interaction.constraint_parser import parse_constraint
from modules.llm_interaction.diff_report import format_diff_summary, generate_diff_report
from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.constraint import ConstraintObject
from shared.schemas.diff_report import DiffReport
from shared.schemas.metrics import MetricsObject
from shared.schemas.placement import PlacementJSON

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
    import tempfile

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


@app.post("/api/placement/generate", response_model=PlacementJSON)
def generate_placement(req: GeneratePlacementRequest):
    """Encodes CircuitGraph using Person A's encoder and generates layout using Person B's flow-matching generator."""
    try:
        encoder = DEHNNEncoder()
        encoder_output = encoder.encode(req.graph)

        generator = PlacementGenerator()
        placement = generator.generate(encoder_output=encoder_output, graph=req.graph, seed=req.seed)
        return placement
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Placement generation failed: {exc}")


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

        diff = generate_diff_report(req.previous_placement, new_placement, constraint)
        summary = format_diff_summary(diff, constraint)

        return EditPlacementResponse(
            requires_clarification=False,
            constraint=constraint,
            new_placement=new_placement,
            diff_report=diff,
            diff_summary=summary,
        )

    except ConstraintRequiresClarificationError as exc:
        return EditPlacementResponse(
            requires_clarification=True,
            clarification_message=str(exc),
            constraint=constraint,
        )
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
