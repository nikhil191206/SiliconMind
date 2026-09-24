/**
 * Facts strip under the hero. Every item is a verifiable fact about the
 * codebase (what's implemented), not a performance claim: benchmark numbers
 * don't exist yet and are never implied here.
 */
import { useReveal } from "../common/useReveal";
import "./StatsStrip.css";

const FACTS = [
  { value: "4", label: "netlist encoders", detail: "GCN · GAT · DE-HNN · DeepGate4" },
  { value: "2", label: "generative engines", detail: "Flow matching · diffusion fallback" },
  { value: "2", label: "baselines to beat", detail: "DREAMPlace · RL (Stable-Baselines3)" },
  { value: "0", label: "legality violations", detail: "Required before anything is called verified" },
];

export function StatsStrip() {
  const ref = useReveal<HTMLElement>();
  return (
    <section ref={ref} className="stats" aria-label="What's in the system">
      <div className="container stats-grid">
        {FACTS.map((f, i) => (
          <div key={f.label} className="stat reveal" style={{ ["--reveal-delay" as string]: `${i * 70}ms` }}>
            <span className="stat-value">{f.value}</span>
            <span className="stat-label">{f.label}</span>
            <span className="stat-detail mono">{f.detail}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
