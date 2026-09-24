/**
 * The five-stage pipeline as a bento grid of tilt cards. Each card names the
 * stage, the module that owns it in the repo, and the real contract it
 * produces: so the landing page reads like the architecture, not marketing.
 */
import type { ReactNode } from "react";
import { useReveal } from "../common/useReveal";
import { EncodeArt, GenerateArt, IntakeArt, RefineArt, VerifyArt } from "./PipelineArt";
import { SectionHead } from "./SectionHead";
import { TiltCard } from "./TiltCard";
import "./PipelineSection.css";

interface Stage {
  step: string;
  title: string;
  body: string;
  module: string;
  output: string;
  art: ReactNode;
  wide?: boolean;
}

const STAGES: Stage[] = [
  {
    step: "01",
    title: "Intake",
    body: "Upload a post-synthesis Verilog netlist or Yosys JSON, or describe a design in plain English and review the drafted RTL before it's synthesized.",
    module: "modules/intake",
    output: "CircuitGraph",
    art: <IntakeArt />,
  },
  {
    step: "02",
    title: "Encode",
    body: "Hypergraph encoders (GCN, GAT, DE-HNN, DeepGate4) turn the netlist into per-node and global embeddings that condition generation.",
    module: "modules/encoders",
    output: "EncoderOutput",
    art: <EncodeArt />,
  },
  {
    step: "03",
    title: "Generate",
    body: "A flow-matching model moves every macro and cell from noise to a placement along straight paths, with diffusion as the fallback.",
    module: "modules/generator",
    output: "PlacementJSON",
    art: <GenerateArt />,
  },
  {
    step: "04",
    title: "Verify",
    body: "DREAMPlace and OpenROAD legalize and score every placement. HPWL, congestion overflow and legality come from one shared implementation, and legality must be zero before anything is labelled verified.",
    module: "modules/evaluation · shared/metrics",
    output: "MetricsObject",
    art: <VerifyArt />,
    wide: true,
  },
  {
    step: "05",
    title: "Refine",
    body: "Say what to change. The request becomes a structured constraint, everything else is frozen, and you get a diff back, or a clarifying question if it's ambiguous.",
    module: "modules/llm_interaction",
    output: "DiffReport",
    art: <RefineArt />,
  },
];

export function PipelineSection() {
  const ref = useReveal<HTMLElement>();
  return (
    <section ref={ref} className="section" aria-labelledby="pipeline-title">
      <span id="pipeline" className="anchor" />
      <div className="container">
        <SectionHead
          id="pipeline-title"
          eyebrow="The pipeline"
          title="From netlist to a placement you can trust."
          lead="Five stages, each owned by one module and connected by typed contracts in shared/schemas. Nothing downstream ever sees raw Verilog, and nothing reaches your screen unverified without a warning attached."
        />
        <div className="pipeline-grid">
          {STAGES.map((s, i) => (
            <TiltCard
              key={s.step}
              className={`pipeline-card reveal ${s.wide ? "is-wide" : ""}`}
            >
              <div className="pipeline-card-body" style={{ ["--reveal-delay" as string]: `${i * 60}ms` }}>
                <div className="pipeline-art grid-backdrop">{s.art}</div>
                <div className="pipeline-text">
                  <div className="pipeline-meta">
                    <span className="caption">{s.step}</span>
                    <span className="badge">{s.output}</span>
                  </div>
                  <h3 className="h5">{s.title}</h3>
                  <p className="muted">{s.body}</p>
                  <p className="pipeline-module mono">{s.module}</p>
                </div>
              </div>
            </TiltCard>
          ))}
        </div>
      </div>
    </section>
  );
}
