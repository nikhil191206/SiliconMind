/**
 * Decorative die layouts for the hero animation.
 *
 * Each layout is a legal (non-overlapping) arrangement of the same macros and
 * cells on the top slab. The scene flows between consecutive layouts via a
 * noise state, the visual idea of flow matching: sample noise, then follow a
 * straight-line trajectory to a placement.
 *
 * This is illustration only; it is never shown as, or mistaken for, a real
 * placement result (the workspace canvas draws real PlacementJSON only).
 */
import { gaussian, mulberry32 } from "../lib/random";

export interface MacroSpec {
  w: number;
  d: number;
}

export interface Layout {
  macros: Array<{ x: number; z: number }>;
  cells: Array<{ x: number; z: number }>;
}

export const MACRO_SPECS: MacroSpec[] = [
  { w: 1.05, d: 0.8 },
  { w: 0.8, d: 0.62 },
  { w: 0.62, d: 0.9 },
  { w: 0.72, d: 0.52 },
  { w: 0.5, d: 0.5 },
  { w: 0.9, d: 0.46 },
  { w: 0.46, d: 0.66 },
];

export const CELL_COUNT = 150;
export const CELL_SIZE = 0.075;

/** Usable half-extent of the die top (slab is 4 wide; keep clear of the rounded rim). */
const HALF = 1.62;

function overlaps(
  a: { x: number; z: number; w: number; d: number },
  b: { x: number; z: number; w: number; d: number },
  gap: number,
): boolean {
  return Math.abs(a.x - b.x) * 2 < a.w + b.w + gap * 2 && Math.abs(a.z - b.z) * 2 < a.d + b.d + gap * 2;
}

export function makeLayout(seed: number): Layout {
  const rand = mulberry32(seed);
  const placed: Array<{ x: number; z: number; w: number; d: number }> = [];

  for (const m of MACRO_SPECS) {
    let best = { x: 0, z: 0 };
    for (let attempt = 0; attempt < 400; attempt++) {
      const x = (rand() * 2 - 1) * (HALF - m.w / 2);
      const z = (rand() * 2 - 1) * (HALF - m.d / 2);
      const cand = { x, z, w: m.w, d: m.d };
      if (!placed.some((p) => overlaps(cand, p, 0.08))) {
        best = { x, z };
        break;
      }
      best = { x, z };
    }
    placed.push({ ...best, w: m.w, d: m.d });
  }

  // Cells cluster around macros (as connected logic would), on a coarse site
  // grid so they never overlap each other or a macro.
  const pitch = CELL_SIZE * 1.9;
  const taken = new Set<string>();
  const cells: Array<{ x: number; z: number }> = [];
  let guard = 0;
  while (cells.length < CELL_COUNT && guard++ < CELL_COUNT * 60) {
    const anchor = placed[Math.floor(rand() * placed.length)];
    const x = anchor.x + gaussian(rand) * 0.55;
    const z = anchor.z + gaussian(rand) * 0.55;
    const gx = Math.round(x / pitch);
    const gz = Math.round(z / pitch);
    const sx = gx * pitch;
    const sz = gz * pitch;
    if (Math.abs(sx) > HALF || Math.abs(sz) > HALF) continue;
    const key = `${gx},${gz}`;
    if (taken.has(key)) continue;
    const cellBox = { x: sx, z: sz, w: CELL_SIZE, d: CELL_SIZE };
    if (placed.some((p) => overlaps(cellBox, p, 0.03))) continue;
    taken.add(key);
    cells.push({ x: sx, z: sz });
  }
  while (cells.length < CELL_COUNT) cells.push({ x: (rand() * 2 - 1) * HALF, z: (rand() * 2 - 1) * HALF });

  return { macros: placed.map((p) => ({ x: p.x, z: p.z })), cells };
}

/** Noise state: positions scattered over (and above) the die. */
export function makeNoise(seed: number, count: number): Array<{ x: number; y: number; z: number }> {
  const rand = mulberry32(seed);
  return Array.from({ length: count }, () => ({
    x: (rand() * 2 - 1) * HALF * 1.05,
    y: 0.35 + rand() * 0.9,
    z: (rand() * 2 - 1) * HALF * 1.05,
  }));
}
