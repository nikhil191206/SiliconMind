/**
 * Plain summary of the CircuitGraph for both personas (spec §3.4 "Success"):
 * "142 macros, 8,203 standard cells, 3,401 nets", plus die size.
 */
import { useMemo } from "react";
import type { CircuitGraph } from "../../../lib/schemas";
import { formatInt, formatNumber } from "../../../lib/format";
import type { Persona } from "../../../state/sessionTypes";
import { Gloss } from "../Gloss";

export function GraphSummary({ graph, persona }: { graph: CircuitGraph; persona: Persona }) {
  const stats = useMemo(() => {
    let macros = 0;
    let pins = 0;
    for (const n of graph.nodes) {
      if (n.type === "MACRO") macros++;
      pins += n.pin_count;
    }
    return { macros, cells: graph.nodes.length - macros, nets: graph.hyperedges.length, pins };
  }, [graph]);

  const items = [
    { label: "Macros", value: formatInt(stats.macros), gloss: "macro" as const },
    { label: "Standard cells", value: formatInt(stats.cells), gloss: "stdCell" as const },
    { label: "Nets", value: formatInt(stats.nets), gloss: "net" as const },
    { label: "Die", value: `${formatNumber(graph.die.width)} × ${formatNumber(graph.die.height)}`, gloss: "die" as const },
  ];

  return (
    <div className="graph-summary">
      <p className="graph-summary-line">
        <strong>{formatInt(stats.macros)}</strong> macros, <strong>{formatInt(stats.cells)}</strong> standard cells,{" "}
        <strong>{formatInt(stats.nets)}</strong> nets
        <span className="faint"> · {formatInt(graph.nodes.length)} nodes total</span>
      </p>
      <dl className="graph-summary-grid">
        {items.map((i) => (
          <div key={i.label}>
            <dt className="caption">{i.label}</dt>
            <dd>
              <span className="graph-summary-value">{i.value}</span>
              <Gloss persona={persona} term={i.gloss} />
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
