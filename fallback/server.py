"""FALLBACK ONLY: FastAPI app serving the endpoints FRONTEND_SPEC.md expects
from backend/main.py, backed by the stand-ins in this folder.

Run from the repo root:
    py -3.14 -m uvicorn fallback.server:app --port 8000 --reload

Honesty rules this server keeps (FRONTEND_SPEC.md §0, TECHNICAL.md 1.4):
  * verification_status is never "verified": nothing here runs DREAMPlace /
    OpenROAD, so every placement is reported as "unavailable: ...".
  * `metrics` is therefore null. Numbers the demo shows come from the extra
    `fallback_report` field, computed ONLY with shared/metrics (Person C's
    real HPWL + legality code), and congestion is reported as not measured.
  * model_variant names the classical placer, never the flow-matching model.

Delete this folder (and the frontend's src/fallback/) once the real backend
exists. See FALLBACK.md.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import shared.env  # noqa: F401 -- loads .env (GROQ_API_KEY/WANDB_API_KEY) as a side effect, same as backend/main.py

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from fallback import FALLBACK_VERSION
from fallback.edit import Parsed, _direction, _region, apply_edit, clarification_message, diff_report, parse_instruction, summarize
from fallback.placer import MODEL_VARIANT, PlacementError, place
from fallback.rtl import IntakeError, draft_rtl, synthesize, yosys_available
from fallback.samples import SAMPLES
from modules.evaluation.packing import grid_pack
from modules.intake.llm_rtl import LLMConfigurationError, synthesize_from_description
from modules.llm_interaction.constraint_parser import parse_constraint
from shared.metrics.hpwl import compute_hpwl
from shared.metrics.legality import compute_legality_violations
from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.constraint import ReferenceType

# Real Groq LLM used for both RTL drafting and NL edit parsing when a key is
# configured (see shared/llm_client.py) -- this project's real LLM
# communication layer, verified working end-to-end before this fallback
# server existed. Only the PLACEMENT algorithm here is a real, honest
# classical stand-in for the untrained flow-matching model (module
# docstring above); there is no reason to *also* substitute a working real
# LLM with a regex/template stand-in just because the generator needs one.
# Falls back to the regex/template versions (fallback.rtl.draft_rtl,
# fallback.edit.parse_instruction) only if no key is configured -- an
# honest, disclosed fallback (the response says so), not a silent one.


def _llm_configured() -> bool:
    import os

    return bool(os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def _parsed_from_llm_constraint(c, graph: CircuitGraph) -> Parsed:
    """Adapts a real ConstraintObject (from the real LLM parser) into
    fallback.edit's own Parsed shape, which _hint_for/apply_edit/summarize
    actually consume. `direction` is unused by _hint_for's execution path
    (confirmed by reading it: NODE references use reference_node, REGION
    references read c.reference.value directly) -- only summarize() uses it,
    purely for a nicer sentence.

    ReferenceType.EDGE is a real, pre-existing ambiguity in the schema: its
    docstring/prompt (modules/llm_interaction/constraint_parser.py) says its
    int `value` should be read like a NODE reference's node_id, but that's
    semantically wrong for "the left/right/top/bottom edge of the die" (an
    edge isn't a node, and in practice the LLM sometimes just echoes back
    the affected node's own id, which would make a macro reference itself --
    confirmed happening with a real request during testing, not a
    hypothetical). Rather than trust that ambiguous int, this re-derives an
    actual die-edge region from the constraint's own source_request text
    using the same left/right/up/down keyword matching fallback.edit's own
    regex parser uses, and swaps it in as a REGION reference -- a defensive,
    disclosed correction of a genuinely ambiguous upstream value, not a
    silent fabrication of new information."""
    if c.reference.type == ReferenceType.EDGE:
        region = _region(_direction(c.source_request), graph.die.width, graph.die.height)
        c = c.model_copy(update={"reference": c.reference.model_copy(update={"value": region})})
        return Parsed(constraint=c, direction=None, reference_node=None)
    reference_node = c.reference.value if c.reference.type == ReferenceType.NODE else None
    return Parsed(constraint=c, direction=None, reference_node=reference_node)
from shared.schemas.placement import GenerationMetadata, PlacementJSON

VERIFICATION_STATUS = (
    "unavailable: fallback mode (classical placer, not the trained model; DREAMPlace/OpenROAD not run)"
)
CONGESTION_NOTE = "Needs OpenROAD + a technology LEF (modules/evaluation/NOTES.md 1.2)."

app = FastAPI(title="SiliconMind FALLBACK backend", version=FALLBACK_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---- request models (field names match frontend/src/lib/api/types.ts) ----


class DraftRTLRequest(BaseModel):
    description: str
    template: Optional[str] = None
    api_key: Optional[str] = None
    design_name: Optional[str] = None


class SynthesizeRTLRequest(BaseModel):
    design_name: str = "top"
    rtl_code: Optional[str] = None
    rtl_path: Optional[str] = None
    yosys_json_data: Any = None


class GeneratePlacementRequest(BaseModel):
    graph: CircuitGraph
    seed: int = 0


class EditPlacementRequest(BaseModel):
    instruction: str
    graph: CircuitGraph
    previous_placement: PlacementJSON
    seed: int = 0
    api_key: Optional[str] = None


# ---- scoring (shared/metrics only) ----


def _score(placement: PlacementJSON, graph: CircuitGraph) -> dict[str, Any]:
    return {
        "hpwl": compute_hpwl(placement, graph),
        "legality_violations": compute_legality_violations(placement, graph),
    }


def _baseline(graph: CircuitGraph) -> dict[str, Any]:
    pj = PlacementJSON(
        design_name=graph.design_name,
        placements=grid_pack(graph.nodes, graph.die),
        generation_metadata=GenerationMetadata(model_variant="grid_pack", seed=0),
    )
    return {"name": "grid_pack (modules/evaluation/packing.py)", **_score(pj, graph)}


def _report(placement: PlacementJSON, graph: CircuitGraph, runtime: float, stages: dict[str, float]) -> dict[str, Any]:
    return {
        "mode": "fallback",
        "method": MODEL_VARIANT,
        "scored_by": "shared/metrics (compute_hpwl, compute_legality_violations)",
        **_score(placement, graph),
        "congestion_overflow": None,
        "congestion_note": CONGESTION_NOTE,
        "runtime_seconds": runtime,
        "stage_seconds": stages,
        "baseline": _baseline(graph),
    }


# ---- fallback-only endpoints ----


@app.get("/api/fallback/status")
def status() -> dict[str, Any]:
    yosys = yosys_available()
    llm_on = _llm_configured()
    real = [
        "CircuitGraph / PlacementJSON / Constraint / DiffReport schemas (shared/schemas)",
        "HPWL and legality scoring (shared/metrics, Person C)",
        "grid_pack baseline (modules/evaluation/packing.py)",
        "Freeze contract: frozen macros are passed through bit-identical, unexpected_moves is computed",
    ]
    substituted = ["Generator: classical placer instead of the untrained flow-matching model (Person B)"]
    if llm_on:
        real += [
            "Edit parser: real LLM constraint parsing (modules/llm_interaction/constraint_parser.py, Person D)",
            "RTL drafting: real LLM synthesis (modules/intake/llm_rtl.py, Person D)",
        ]
    else:
        substituted += [
            "Edit parser: rule-based regexes instead of the LLM parser (Person D) -- no GROQ_API_KEY/OPENAI_API_KEY set",
            "RTL drafting: templates instead of the LLM (Person D) -- no GROQ_API_KEY/OPENAI_API_KEY set",
        ]
    substituted.append(
        "Synthesis: " + ("local Yosys" if yosys else "size ESTIMATE from RTL, Yosys not installed") + " (Person D)"
    )
    return {
        "fallback": True,
        "version": FALLBACK_VERSION,
        "yosys": yosys,
        "llm_configured": llm_on,
        "real": real,
        "substituted": substituted,
        "not_run": ["DREAMPlace legalization", "OpenROAD congestion", "verification (status is never 'verified')"],
    }


@app.get("/api/fallback/samples")
def list_samples() -> list[dict[str, str]]:
    return [{"id": k, "label": v["label"], "description": v["description"]} for k, v in SAMPLES.items()]


@app.get("/api/fallback/samples/{sample_id}")
def get_sample(sample_id: str) -> CircuitGraph:
    if sample_id not in SAMPLES:
        raise HTTPException(404, f"Unknown sample '{sample_id}'.")
    return SAMPLES[sample_id]["build"]()


# ---- spec endpoints ----


@app.post("/api/intake/draft-rtl")
def draft(req: DraftRTLRequest) -> dict[str, str]:
    if not req.description.strip():
        raise HTTPException(422, "Description is empty.")
    if req.api_key or _llm_configured():
        try:
            return {"rtl_code": synthesize_from_description(req.description, template=req.template, api_key=req.api_key, provider="groq")}
        except LLMConfigurationError as e:
            raise HTTPException(400, str(e)) from e
    return {"rtl_code": draft_rtl(req.description, req.design_name)}


@app.post("/api/intake/synthesize")
def synth(req: SynthesizeRTLRequest) -> CircuitGraph:
    try:
        graph, _note = synthesize(req.design_name, req.rtl_code, req.rtl_path, req.yosys_json_data)
    except IntakeError as e:
        raise HTTPException(422, str(e)) from e
    except ValueError as e:  # schema validation of a pasted CircuitGraph
        raise HTTPException(422, f"Not a valid netlist: {e}") from e
    return graph


@app.post("/api/placement/generate")
def generate(req: GeneratePlacementRequest) -> dict[str, Any]:
    t = time.perf_counter()
    try:
        res = place(req.graph, seed=req.seed)
    except PlacementError as e:
        raise HTTPException(422, str(e)) from e
    runtime = time.perf_counter() - t
    return {
        "placement": res.placement.model_dump(mode="json"),
        "metrics": None,
        "verification_status": VERIFICATION_STATUS,
        "fallback_report": _report(res.placement, req.graph, runtime, res.stage_seconds),
    }


@app.post("/api/placement/edit")
def edit(req: EditPlacementRequest) -> dict[str, Any]:
    if req.api_key or _llm_configured():
        real_constraint = parse_constraint(req.instruction, req.previous_placement, graph=req.graph, api_key=req.api_key)
        parsed = _parsed_from_llm_constraint(real_constraint, req.graph)
    else:
        parsed = parse_instruction(req.instruction, req.graph)
    c = parsed.constraint
    base = {
        "constraint": c.model_dump(mode="json"),
        "new_placement": None,
        "metrics_before": None,
        "metrics_after": None,
        "verification_status": None,
        "diff_report": None,
        "diff_summary": None,
    }
    if c.requires_clarification():
        # Hard rule (TECHNICAL.md 3.4): the generator is NOT called.
        return {**base, "requires_clarification": True, "clarification_message": clarification_message(req.instruction, c)}

    t = time.perf_counter()
    try:
        new = apply_edit(parsed, req.graph, req.previous_placement, req.seed)
    except PlacementError as e:
        raise HTTPException(422, str(e)) from e
    runtime = time.perf_counter() - t
    before = _score(req.previous_placement, req.graph)
    report = _report(new, req.graph, runtime, {"total": runtime})
    diff = diff_report(c, req.previous_placement, new, before["hpwl"], report["hpwl"])
    return {
        **base,
        "requires_clarification": False,
        "clarification_message": None,
        "new_placement": new.model_dump(mode="json"),
        "verification_status": VERIFICATION_STATUS,
        "diff_report": diff.model_dump(mode="json"),
        "diff_summary": summarize(parsed, req.graph, diff, before["hpwl"], report["hpwl"]),
        "fallback_report": {**report, "before": before},
    }
