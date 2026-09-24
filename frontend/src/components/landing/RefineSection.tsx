/**
 * Natural-language refinement, shown as a looping scripted example: the
 * instruction types itself, then the structured ConstraintObject and the
 * outcome appear. The second script demonstrates the clarification path
 * (confidence < 0.6 → ask, don't guess). Example output only, no metrics.
 */
import { useEffect, useState } from "react";
import { Icon } from "../common/Icon";
import { useReveal } from "../common/useReveal";
import { SectionHead } from "./SectionHead";
import "./RefineSection.css";

interface Script {
  instruction: string;
  constraint: string;
  outcome: { kind: "ok" | "ask"; text: string };
}

const SCRIPTS: Script[] = [
  {
    instruction: "move macros 3 and 5 away from macro 0",
    constraint: `{
  "constraint_type": "MOVE_AWAY_FROM",
  "affected_node_ids": [3, 5],
  "reference": { "type": "NODE", "value": 0 },
  "strength": "SOFT",
  "confidence": 0.9
}`,
    outcome: {
      kind: "ok",
      text: "Moved 2 macros (3, 5). Every other node was frozen and is bit-identical. unexpected_moves: []",
    },
  },
  {
    instruction: "make it better",
    constraint: `{
  "constraint_type": "UNCLEAR",
  "affected_node_ids": [],
  "confidence": 0.2
}`,
    outcome: {
      kind: "ask",
      text: "Ambiguous or low confidence (0.20). Which macros, and which direction? e.g. 'move macro 3 toward the left edge'.",
    },
  },
];

type Phase = "typing" | "parsing" | "result" | "hold";

export function RefineSection() {
  const ref = useReveal<HTMLElement>();
  const [idx, setIdx] = useState(0);
  const [typed, setTyped] = useState(0);
  const [phase, setPhase] = useState<Phase>("typing");
  const script = SCRIPTS[idx];

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setTyped(script.instruction.length);
      setPhase("result");
      return;
    }
    let timer: number;
    if (phase === "typing") {
      if (typed < script.instruction.length) {
        timer = window.setTimeout(() => setTyped((n) => n + 1), 38 + Math.random() * 40);
      } else {
        timer = window.setTimeout(() => setPhase("parsing"), 380);
      }
    } else if (phase === "parsing") {
      timer = window.setTimeout(() => setPhase("result"), 900);
    } else if (phase === "result") {
      timer = window.setTimeout(() => setPhase("hold"), 3600);
    } else {
      timer = window.setTimeout(() => {
        setIdx((i) => (i + 1) % SCRIPTS.length);
        setTyped(0);
        setPhase("typing");
      }, 300);
    }
    return () => window.clearTimeout(timer);
  }, [phase, typed, script.instruction.length]);

  const showResult = phase === "result";

  return (
    <section ref={ref} className="section section-soft" aria-labelledby="refine-title">
      <span id="refine" className="anchor" />
      <div className="container refine-grid">
        <div>
          <SectionHead
            id="refine-title"
            eyebrow="Natural-language refinement"
            title="Talk to the placement."
            lead="Select macros on the canvas or name them, then say what should change. Your words become a structured constraint, everything you didn't mention stays frozen, and you get a diff you can inspect, compare and undo."
          />
          <ul className="refine-points reveal">
            <li>
              <Icon name="target" size={16} /> Frozen means frozen, enforced at the tensor level
            </li>
            <li>
              <Icon name="help" size={16} /> Below 0.6 confidence it asks instead of guessing
            </li>
            <li>
              <Icon name="history" size={16} /> Branching history: jump back to any state
            </li>
          </ul>
        </div>

        <div className="refine-demo reveal" aria-live="off">
          <div className="refine-window">
            <div className="refine-window-bar">
              <span />
              <span />
              <span />
              <p className="mono">example · /api/placement/edit</p>
            </div>

            <div className="refine-body">
              <div className="refine-input">
                <Icon name="message" size={16} />
                <span className="refine-typed">
                  {script.instruction.slice(0, typed)}
                  {phase === "typing" && <span className="refine-caret" />}
                </span>
                <span className={`refine-send ${phase !== "typing" ? "is-sent" : ""}`}>
                  <Icon name="send" size={14} />
                </span>
              </div>

              <div className={`refine-step ${phase !== "typing" ? "is-in" : ""}`}>
                <p className="caption">
                  ConstraintObject
                  {phase === "parsing" && <span className="spinner refine-spin" />}
                </p>
                <pre className="code-block refine-code">
                  <code>{phase === "typing" ? " " : script.constraint}</code>
                </pre>
              </div>

              <div className={`refine-step ${showResult ? "is-in" : ""}`}>
                <div className={`refine-outcome ${script.outcome.kind === "ok" ? "is-ok" : "is-ask"}`}>
                  <Icon name={script.outcome.kind === "ok" ? "checkCircle" : "help"} size={16} />
                  <div>
                    <strong>{script.outcome.kind === "ok" ? "diff_summary" : "Needs clarification"}</strong>
                    <p>{script.outcome.text}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
