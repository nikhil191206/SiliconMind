/** Site footer: product links, repo docs, and the team's module ownership. */
import { Link } from "react-router-dom";
import { Logo } from "../common/Logo";
import { REPO_URL } from "./SiteHeader";
import "./SiteFooter.css";

const DOCS = [
  { label: "README", href: `${REPO_URL}#readme` },
  { label: "TECHNICAL.md", href: `${REPO_URL}/blob/main/TECHNICAL.md` },
  { label: "FRONTEND_SPEC.md", href: `${REPO_URL}/blob/main/FRONTEND_SPEC.md` },
  { label: "CONTRIBUTING", href: `${REPO_URL}/blob/main/CONTRIBUTING.md` },
];

const MODULES = [
  { label: "Encoders", path: "modules/encoders" },
  { label: "Generator", path: "modules/generator" },
  { label: "Evaluation", path: "modules/evaluation" },
  { label: "Intake & LLM", path: "modules/intake" },
];

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="container site-footer-grid">
        <div className="site-footer-brand">
          <Logo />
          <p className="muted">Generative chip placement with a verified, natural-language refinement loop.</p>
        </div>

        <nav aria-label="Product">
          <p className="caption">Product</p>
          <ul>
            <li>
              <Link to="/app">Workspace</Link>
            </li>
            <li>
              <a href="#pipeline">Pipeline</a>
            </li>
            <li>
              <a href="#verification">Verification</a>
            </li>
            <li>
              <a href="#benchmarks">Benchmarks</a>
            </li>
          </ul>
        </nav>

        <nav aria-label="Documentation">
          <p className="caption">Docs</p>
          <ul>
            {DOCS.map((d) => (
              <li key={d.label}>
                <a href={d.href} target="_blank" rel="noreferrer">
                  {d.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <nav aria-label="Modules">
          <p className="caption">Modules</p>
          <ul>
            {MODULES.map((m) => (
              <li key={m.path}>
                <a href={`${REPO_URL}/tree/main/${m.path}`} target="_blank" rel="noreferrer">
                  {m.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </div>
      <div className="container site-footer-bottom">
        <span className="mono">SiliconMind · EDI project</span>
        <span className="mono">Visualization draws geometry only, never a generative image.</span>
      </div>
    </footer>
  );
}
