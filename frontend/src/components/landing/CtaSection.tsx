/** Closing call-to-action with a rainbow-bordered panel and a single rainbow slab. */
import { Link } from "react-router-dom";
import { Icon } from "../common/Icon";
import { useReveal } from "../common/useReveal";
import { SceneCanvas } from "./SceneCanvas";
import "./CtaSection.css";

export function CtaSection() {
  const ref = useReveal<HTMLElement>();
  return (
    <section ref={ref} className="section cta">
      <div className="container">
        <div className="cta-panel reveal">
          <div className="cta-copy">
            <h2 className="h2">Place your first design.</h2>
            <p className="lead">
              Upload a netlist, or describe what you want to build. Demo mode runs entirely in your browser until the
              backend is connected.
            </p>
            <div className="cta-actions">
              <Link to="/app" className="btn btn-primary btn-lg">
                Open the workspace <Icon name="arrowRight" size={16} />
              </Link>
            </div>
          </div>
          <div className="cta-visual" aria-hidden="true">
            <SceneCanvas layers={["rainbow"]} frustum={2.3} pointer={false} offsetY={0} grain={0.05} />
          </div>
        </div>
      </div>
    </section>
  );
}
