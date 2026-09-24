/**
 * "Verified, or it says so.": explains the three non-negotiable UI rules
 * from FRONTEND_SPEC.md §0 and previews the exact status treatments the
 * workspace uses, next to a second (sandwich) slab stack.
 */
import { Icon } from "../common/Icon";
import { useReveal } from "../common/useReveal";
import { SceneCanvas } from "./SceneCanvas";
import { SectionHead } from "./SectionHead";
import "./VerificationSection.css";

const RULES = [
  {
    icon: "shield" as const,
    title: "Unverified never looks final",
    body: "If DREAMPlace or OpenROAD couldn't check a placement, a banner you can't dismiss says so, and the metrics show as unavailable rather than zero.",
  },
  {
    icon: "chart" as const,
    title: "No invented progress or numbers",
    body: "Generation shows an honest indeterminate state sized to the real node count. There are no fake percentages and no placeholder chips.",
  },
  {
    icon: "alertOctagon" as const,
    title: "Contradictions are errors",
    body: "A \"verified\" placement with legality violations, or an edit that moved frozen nodes, is an upstream bug. It's shown loudly as one, with diagnostics you can copy.",
  },
];

export function VerificationSection() {
  const ref = useReveal<HTMLElement>();
  return (
    <section ref={ref} className="section" aria-labelledby="verify-title">
      <span id="verification" className="anchor" />
      <div className="container verify-grid">
        <div className="verify-visual reveal">
          <SceneCanvas layers={["matte", "rainbow", "matte"]} frustum={2.9} gap={0.62} pointer offsetY={0} />
        </div>

        <div className="verify-copy">
          <SectionHead
            id="verify-title"
            eyebrow="Verification contract"
            title={
              <>
                Verified, <span className="muted">or it says so.</span>
              </>
            }
            lead="The visualizer only draws verified PlacementJSON geometry. No generative image model is involved at any step. Every number on screen traces back to shared/metrics."
          />

          <ul className="verify-rules">
            {RULES.map((r, i) => (
              <li key={r.title} className="verify-rule reveal" style={{ ["--reveal-delay" as string]: `${i * 80}ms` }}>
                <span className="verify-rule-icon">
                  <Icon name={r.icon} size={18} />
                </span>
                <div>
                  <h3 className="verify-rule-title">{r.title}</h3>
                  <p className="muted">{r.body}</p>
                </div>
              </li>
            ))}
          </ul>

          <div className="verify-states reveal" aria-label="Status treatments used in the workspace">
            <div className="verify-state is-ok">
              <Icon name="checkCircle" size={16} />
              <span>
                <strong>Verified</strong> · legalized by DREAMPlace
              </span>
            </div>
            <div className="verify-state is-warn">
              <Icon name="alertTriangle" size={16} />
              <span>
                <strong>Not verified</strong> · legalizer unavailable
              </span>
            </div>
            <div className="verify-state is-danger">
              <Icon name="alertOctagon" size={16} />
              <span>
                <strong>Internal inconsistency</strong> · report it
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
