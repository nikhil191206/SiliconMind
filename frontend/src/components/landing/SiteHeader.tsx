/**
 * Landing-page header: sticky, translucent, hairline bottom border that only
 * appears once the page has scrolled (rerun.io behaviour). Collapses to a
 * menu button under 760px.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Icon } from "../common/Icon";
import { Logo } from "../common/Logo";
import "./SiteHeader.css";

const NAV = [
  { href: "#pipeline", label: "Pipeline" },
  { href: "#flow", label: "Flow matching" },
  { href: "#verification", label: "Verification" },
  { href: "#refine", label: "Refine" },
  { href: "#benchmarks", label: "Benchmarks" },
];

/** Canonical repo link (this checkout's origin). Change here only. */
export const REPO_URL = "https://github.com/Raginipawar/SiliconMind";

export function SiteHeader() {
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className={`site-header ${scrolled ? "is-scrolled" : ""}`}>
      <div className="container site-header-inner">
        <Link to="/" className="site-header-logo" aria-label="SiliconMind home">
          <Logo />
        </Link>

        <nav className="site-nav" aria-label="Primary">
          {NAV.map((n) => (
            <a key={n.href} href={n.href} className="site-nav-link">
              {n.label}
            </a>
          ))}
        </nav>

        <div className="site-header-actions">
          <a className="btn btn-ghost btn-icon" href={REPO_URL} target="_blank" rel="noreferrer" aria-label="GitHub repository">
            <Icon name="git" size={18} />
          </a>
          <Link to="/app" className="btn btn-primary site-header-cta">
            Open workspace
          </Link>
          <button
            type="button"
            className="btn btn-ghost btn-icon site-menu-btn"
            aria-expanded={menuOpen}
            aria-controls="mobile-nav"
            aria-label="Menu"
            onClick={() => setMenuOpen((v) => !v)}
          >
            <Icon name={menuOpen ? "x" : "list"} size={18} />
          </button>
        </div>
      </div>

      {menuOpen && (
        <nav id="mobile-nav" className="mobile-nav" aria-label="Primary (mobile)">
          {NAV.map((n) => (
            <a key={n.href} href={n.href} onClick={() => setMenuOpen(false)}>
              {n.label}
            </a>
          ))}
          <Link to="/app" className="btn btn-primary" onClick={() => setMenuOpen(false)}>
            Open workspace
          </Link>
        </nav>
      )}
    </header>
  );
}
