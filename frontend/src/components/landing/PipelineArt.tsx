/**
 * Small, lightly animated SVG illustrations for the five pipeline cards.
 * Decorative only (aria-hidden); the card text carries the meaning.
 */
import "./PipelineArt.css";

export function IntakeArt() {
  return (
    <svg viewBox="0 0 320 150" className="art" aria-hidden="true">
      <rect x="12" y="16" width="150" height="118" rx="10" className="art-code-bg" />
      <g className="art-mono">
        <text x="26" y="40">
          <tspan className="art-kw">module</tspan> alu (
        </text>
        <text x="38" y="58">
          <tspan className="art-kw">input</tspan> [15:0] a,
        </text>
        <text x="38" y="76">
          <tspan className="art-kw">input</tspan> [15:0] b,
        </text>
        <text x="38" y="94">
          <tspan className="art-kw">output</tspan> y );
        </text>
        <text x="26" y="118">
          <tspan className="art-kw">endmodule</tspan>
        </text>
      </g>
      <path d="M172 75h34" className="art-arrow" />
      <path d="M200 69l7 6-7 6" className="art-arrow" />
      <g className="art-graph">
        <line x1="236" y1="44" x2="282" y2="62" />
        <line x1="236" y1="44" x2="246" y2="104" />
        <line x1="282" y1="62" x2="246" y2="104" />
        <line x1="282" y1="62" x2="298" y2="116" />
        <line x1="246" y1="104" x2="298" y2="116" />
        <rect x="224" y="34" width="24" height="18" rx="4" className="art-macro" />
        <circle cx="282" cy="62" r="6" />
        <circle cx="246" cy="104" r="6" />
        <circle cx="298" cy="116" r="6" />
      </g>
    </svg>
  );
}

export function EncodeArt() {
  const nodes = [
    [60, 40],
    [120, 30],
    [180, 55],
    [90, 95],
    [150, 110],
    [230, 90],
    [260, 40],
  ];
  return (
    <svg viewBox="0 0 320 150" className="art" aria-hidden="true">
      <g className="art-hyperedge">
        <path d="M50 30 Q120 5 190 50 Q150 80 85 105 Q40 70 50 30z" />
        <path d="M140 100 Q200 60 270 35 Q285 90 235 105 Q180 130 140 100z" />
      </g>
      <g className="art-graph">
        {nodes.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="7" className="art-node" style={{ animationDelay: `${i * 0.25}s` }} />
        ))}
      </g>
      <g className="art-embed">
        {Array.from({ length: 8 }, (_, i) => (
          <rect key={i} x={24 + i * 34} y="132" width="28" height="8" rx="2" style={{ animationDelay: `${i * 0.12}s` }} />
        ))}
      </g>
    </svg>
  );
}

export function GenerateArt() {
  const targets = [
    [40, 30, 50, 34],
    [110, 26, 40, 46],
    [170, 34, 58, 30],
    [240, 24, 48, 40],
    [60, 92, 64, 30],
    [150, 90, 44, 40],
    [220, 96, 60, 30],
  ];
  return (
    <svg viewBox="0 0 320 150" className="art" aria-hidden="true">
      <rect x="18" y="12" width="284" height="126" rx="8" className="art-die" />
      {targets.map(([x, y, w, h], i) => (
        <g key={i} className="art-flow" style={{ animationDelay: `${i * 0.18}s` }}>
          <rect x={x} y={y} width={w} height={h} rx="4" className={i === 2 ? "art-macro-rb" : "art-macro"} />
        </g>
      ))}
    </svg>
  );
}

export function VerifyArt() {
  return (
    <svg viewBox="0 0 640 150" className="art" aria-hidden="true">
      {[
        // Formulas, not results: no benchmark numbers exist yet (TECHNICAL.md §1.4).
        ["HPWL", "Σ Δx + Δy", 0],
        ["Congestion", "Σ max(0, d−c)", 1],
        ["Legality", "= 0", 2],
      ].map(([label, value, i]) => (
        <g key={label as string} transform={`translate(${20 + (i as number) * 206} 22)`}>
          <rect width="190" height="106" rx="10" className="art-card" />
          <text x="16" y="30" className="art-label">
            {label}
          </text>
          <text x="16" y="72" className="art-value">
            {value}
          </text>
          {i === 2 && (
            <g transform="translate(150 16)">
              <circle r="12" cx="12" cy="12" className="art-ok-bg" />
              <path d="M6 12l4 4 8-8" className="art-ok" />
            </g>
          )}
        </g>
      ))}
    </svg>
  );
}

export function RefineArt() {
  return (
    <svg viewBox="0 0 320 150" className="art" aria-hidden="true">
      <rect x="14" y="14" width="200" height="34" rx="17" className="art-bubble" />
      <text x="30" y="36" className="art-bubble-text">
        move m3 away from m7
      </text>
      <rect x="18" y="62" width="284" height="76" rx="8" className="art-die" />
      <rect x="40" y="76" width="50" height="34" rx="4" className="art-macro" />
      <rect x="230" y="84" width="54" height="40" rx="4" className="art-macro" />
      <g className="art-move">
        <rect x="104" y="80" width="46" height="36" rx="4" className="art-macro-rb" />
      </g>
      <path d="M150 98h48" className="art-trail" />
    </svg>
  );
}
