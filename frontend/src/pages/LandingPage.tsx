/**
 * Landing page (rerun.io-inspired): white canvas, system sans + JetBrains
 * Mono, a live 3D slab stack in the hero, rainbow used as a sparing accent.
 */
import { BenchmarksSection } from "../components/landing/BenchmarksSection";
import { CtaSection } from "../components/landing/CtaSection";
import { FlowSection } from "../components/landing/FlowSection";
import { Hero } from "../components/landing/Hero";
import { PipelineSection } from "../components/landing/PipelineSection";
import { RefineSection } from "../components/landing/RefineSection";
import { SiteFooter } from "../components/landing/SiteFooter";
import { SiteHeader } from "../components/landing/SiteHeader";
import { StatsStrip } from "../components/landing/StatsStrip";
import { VerificationSection } from "../components/landing/VerificationSection";
import "../components/landing/landing.css";

export function LandingPage() {
  return (
    <>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <SiteHeader />
      <main id="main">
        <Hero />
        <StatsStrip />
        <PipelineSection />
        <FlowSection />
        <VerificationSection />
        <RefineSection />
        <BenchmarksSection />
        <CtaSection />
      </main>
      <SiteFooter />
    </>
  );
}
