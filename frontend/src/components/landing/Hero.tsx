/**
 * Landing hero: headline + CTAs on the left, the live 3D die stack on the
 * right. The stack separates as you scroll away (exploded view).
 */
import { Link } from "react-router-dom";
import { Icon } from "../common/Icon";
import { SceneCanvas } from "./SceneCanvas";
import { REPO_URL } from "./SiteHeader";
import "./Hero.css";

export function Hero() {
  return (
    <section className="hero">
      <div className="container hero-grid">
        <div className="hero-copy">
          <p className="caption hero-eyebrow">
            <span className="hero-dot" aria-hidden="true" />
            Generative AI for chip placement
          </p>
          <h1 className="h1 hero-title">
            Chip placement,
            <br />
            generated <span className="hero-title-soft">and verified.</span>
          </h1>
          <p className="lead hero-lead">
            SiliconMind turns a synthesized netlist into a macro and standard-cell placement with a flow-matching
            model, checks every result with DREAMPlace and OpenROAD, and lets you refine it in plain English.
          </p>
          <div className="hero-actions">
            <Link to="/app" className="btn btn-primary btn-lg">
              Open the workspace
              <Icon name="arrowRight" size={16} />
            </Link>
            <a href={REPO_URL} target="_blank" rel="noreferrer" className="btn btn-rainbow btn-lg">
              <Icon name="git" size={16} />
              View source
            </a>
          </div>

          <div className="hero-pipeline mono" aria-label="Pipeline: netlist to verified placement">
            <span>netlist.v</span>
            <Icon name="arrowRight" size={12} />
            <span>CircuitGraph</span>
            <Icon name="arrowRight" size={12} />
            <span>PlacementJSON</span>
            <Icon name="arrowRight" size={12} />
            <span className="hero-pipeline-ok">
              <Icon name="check" size={12} /> verified
            </span>
          </div>
        </div>

        <div className="hero-visual">
          <SceneCanvas layers={["rainbow", "matte", "die"]} scrollSpread />
          <p className="hero-visual-caption mono">
            Illustration: macros and cells flowing from noise to a legal placement
          </p>
        </div>
      </div>
    </section>
  );
}
