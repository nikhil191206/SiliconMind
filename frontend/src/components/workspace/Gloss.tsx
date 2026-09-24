/**
 * Plain-English gloss for technical terms (spec §1.1). In Beginner persona
 * the explanation is rendered inline as subtext; in Expert it's hidden
 * entirely so it doesn't get in the way.
 */
import type { Persona } from "../../state/sessionTypes";

export const GLOSSARY = {
  hpwl: "Lower is better: roughly how much wire the chip needs",
  congestion: "Lower is better: how crowded the wiring gets in tight areas",
  legality: "Must be 0 in a finished design: overlapping or out-of-bounds components",
  macro: "A large pre-built block, like a memory; the pieces you usually reason about and move",
  stdCell: "A tiny logic gate. Real designs have thousands to millions of them",
  net: "A wire connecting several components",
  netlist: "A list of all components in a design and how they're wired together",
  placement: "Where every component sits on the chip",
  seed: "A number that makes generation repeatable: same seed, same result",
  die: "The chip's outline: everything has to fit inside it",
} as const;

export function Gloss({ persona, term }: { persona: Persona; term: keyof typeof GLOSSARY }) {
  if (persona !== "beginner") return null;
  return <span className="gloss">{GLOSSARY[term]}</span>;
}
