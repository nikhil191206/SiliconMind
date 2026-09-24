/**
 * Benchmarks: deliberately honest. The evaluation protocol (TECHNICAL.md
 * §1.9) is real and published; the results table is empty because the models
 * have not been trained on real chips yet. Each cell says "Pending" rather
 * than showing a number that doesn't exist.
 */
import { Icon } from "../common/Icon";
import { useReveal } from "../common/useReveal";
import { SectionHead } from "./SectionHead";
import "./BenchmarksSection.css";

const METRICS = [
  { name: "HPWL", note: "total half-perimeter wirelength" },
  { name: "Congestion overflow", note: "routing demand over capacity" },
  { name: "Legality violations", note: "must be 0" },
  { name: "Runtime", note: "same hardware for every method" },
];

const METHODS = ["SiliconMind", "DREAMPlace", "RL baseline"];

const PROTOCOL = [
  "Every result reported against DREAMPlace and the RL baseline on the same design.",
  "At least 5 random seeds per configuration, reported as mean ± std.",
  "Paired t-test or Wilcoxon (p < 0.05) before any claim of superiority.",
  "Fixed train/test chip split, defined once in the shared config.",
  "Drift benchmark: ≥ 10 sequential edits, measuring unrelated macros that moved.",
  "LLM constraint accuracy on ≥ 100 held-out request → constraint pairs.",
];

export function BenchmarksSection() {
  const ref = useReveal<HTMLElement>();
  return (
    <section ref={ref} className="section" aria-labelledby="bench-title">
      <span id="benchmarks" className="anchor" />
      <div className="container">
        <SectionHead
          id="bench-title"
          eyebrow="Benchmarks"
          title="Measured, not assumed."
          lead="Results will be published against the classical and RL placers under a fixed protocol. Until the models are trained on real benchmark chips, this table stays empty rather than showing numbers that don't exist."
        />

        <div className="bench-grid">
          <div className="bench-table-wrap reveal">
            <table className="bench-table">
              <caption className="visually-hidden">Benchmark results (pending real data)</caption>
              <thead>
                <tr>
                  <th scope="col">Metric</th>
                  {METHODS.map((m) => (
                    <th key={m} scope="col">
                      {m}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {METRICS.map((m) => (
                  <tr key={m.name}>
                    <th scope="row">
                      <span>{m.name}</span>
                      <small>{m.note}</small>
                    </th>
                    {METHODS.map((method) => (
                      <td key={method}>
                        <span className="bench-pending mono">Pending</span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="bench-foot mono">
              <Icon name="info" size={13} /> Awaiting real-chip training runs · ISPD / ICCAD benchmark suites
            </p>
          </div>

          <div className="bench-protocol reveal">
            <p className="caption">Evaluation protocol</p>
            <ol>
              {PROTOCOL.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ol>
          </div>
        </div>
      </div>
    </section>
  );
}
