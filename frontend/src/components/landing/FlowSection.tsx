/**
 * Interactive flow-matching explainer.
 *
 * Shows the rectified-flow interpolation x_t = (1 − t)·x₀ + t·x₁ on a toy die:
 * x₀ are Gaussian noise samples, x₁ a legal macro placement, and each macro
 * travels its straight trajectory as t goes 0 → 1. Scrub with the slider or
 * let it auto-play. Clearly labelled as an illustration.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { gaussian, mulberry32 } from "../../lib/random";
import { Icon } from "../common/Icon";
import { useReveal } from "../common/useReveal";
import { SectionHead } from "./SectionHead";
import "./FlowSection.css";

interface Macro {
  w: number;
  h: number;
  x1: number;
  y1: number;
}

// Legal target placement on a 100×70 die (lower-left origin, like PlacementJSON).
const TARGET: Macro[] = [
  { w: 22, h: 16, x1: 4, y1: 50 },
  { w: 16, h: 20, x1: 30, y1: 46 },
  { w: 26, h: 12, x1: 70, y1: 54 },
  { w: 14, h: 14, x1: 82, y1: 30 },
  { w: 20, h: 14, x1: 4, y1: 6 },
  { w: 18, h: 10, x1: 30, y1: 4 },
  { w: 12, h: 18, x1: 56, y1: 6 },
  { w: 22, h: 12, x1: 74, y1: 6 },
  { w: 16, h: 12, x1: 44, y1: 28 },
];
const DIE_W = 100;
const DIE_H = 70;

function sampleNoise(seed: number) {
  const r = mulberry32(seed);
  return TARGET.map(() => ({ x0: 50 + gaussian(r) * 26, y0: 35 + gaussian(r) * 18 }));
}

const easeInOut = (t: number) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);

export function FlowSection() {
  const sectionRef = useReveal<HTMLElement>();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [seed, setSeed] = useState(7);
  const noise = useRef(sampleNoise(seed));
  const inView = useRef(false);

  useEffect(() => {
    noise.current = sampleNoise(seed);
  }, [seed]);

  const draw = useCallback((tv: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const cssW = canvas.clientWidth;
    const cssH = canvas.clientHeight;
    if (canvas.width !== Math.round(cssW * dpr) || canvas.height !== Math.round(cssH * dpr)) {
      canvas.width = Math.round(cssW * dpr);
      canvas.height = Math.round(cssH * dpr);
    }
    const ctx = canvas.getContext("2d")!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    const pad = 18;
    const s = Math.min((cssW - pad * 2) / DIE_W, (cssH - pad * 2) / DIE_H);
    const ox = (cssW - DIE_W * s) / 2;
    const oy = (cssH - DIE_H * s) / 2;
    // die → screen (flip Y: die origin is lower-left)
    const X = (x: number) => ox + x * s;
    const Y = (y: number) => oy + (DIE_H - y) * s;

    // Die outline
    ctx.strokeStyle = "#0a0a0a";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(X(0), Y(DIE_H), DIE_W * s, DIE_H * s);

    const rainbow = ctx.createLinearGradient(0, 0, cssW, 0);
    ["#669ef0", "#80d9c7", "#f7ed8c", "#fca65c", "#f75c6b"].forEach((c, i) => rainbow.addColorStop(i / 4, c));

    TARGET.forEach((m, i) => {
      const n = noise.current[i];
      // Centres travel in a straight line; x₀ is the centre's noise sample.
      const cx0 = n.x0;
      const cy0 = n.y0;
      const cx1 = m.x1 + m.w / 2;
      const cy1 = m.y1 + m.h / 2;
      const cx = (1 - tv) * cx0 + tv * cx1;
      const cy = (1 - tv) * cy0 + tv * cy1;

      // Full trajectory (faint) + travelled part (solid)
      ctx.setLineDash([3, 4]);
      ctx.strokeStyle = "#d4d4d4";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(X(cx0), Y(cy0));
      ctx.lineTo(X(cx1), Y(cy1));
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.strokeStyle = "#a3a3a3";
      ctx.beginPath();
      ctx.moveTo(X(cx0), Y(cy0));
      ctx.lineTo(X(cx), Y(cy));
      ctx.stroke();

      // Noise origin
      ctx.fillStyle = "#a3a3a3";
      ctx.beginPath();
      ctx.arc(X(cx0), Y(cy0), 2.2, 0, Math.PI * 2);
      ctx.fill();

      // Target ghost
      ctx.strokeStyle = "rgba(10,10,10,0.18)";
      ctx.setLineDash([2, 3]);
      ctx.strokeRect(X(m.x1), Y(m.y1 + m.h), m.w * s, m.h * s);
      ctx.setLineDash([]);

      // Macro at x_t: grows from a point-like sample into its footprint.
      const k = 0.25 + 0.75 * tv;
      const w = m.w * k;
      const h = m.h * k;
      ctx.globalAlpha = 0.35 + 0.65 * tv;
      ctx.fillStyle = i === 2 ? rainbow : "#262626";
      const rx = X(cx - w / 2);
      const ry = Y(cy + h / 2);
      ctx.beginPath();
      ctx.roundRect(rx, ry, w * s, h * s, 3);
      ctx.fill();
      ctx.globalAlpha = 1;
    });
  }, []);

  // Auto-play loop (only while visible and playing).
  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const io = new IntersectionObserver((e) => (inView.current = e[0].isIntersecting), { threshold: 0.1 });
    io.observe(el);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    let phase = 0;
    let last = 0;
    const loop = (now: number) => {
      const dt = last ? (now - last) / 1000 : 0;
      last = now;
      if (playing && inView.current && !reduce) {
        phase = (phase + dt / 5.5) % 1; // 5.5 s cycle: hold at ends
        const tri = phase < 0.1 ? 0 : phase < 0.62 ? easeInOut((phase - 0.1) / 0.52) : phase < 0.9 ? 1 : 1 - easeInOut((phase - 0.9) / 0.1);
        setT(tri);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
    };
  }, [playing]);

  useEffect(() => {
    draw(t);
  }, [t, seed, draw]);

  useEffect(() => {
    const onResize = () => draw(t);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [draw, t]);

  return (
    <section ref={sectionRef} className="section section-soft" aria-labelledby="flow-title">
      <span id="flow" className="anchor" />
      <div className="container flow-grid">
        <div>
          <SectionHead
            id="flow-title"
            eyebrow="Flow matching"
            title="Noise in, placement out, along straight lines."
            lead="The generator learns a velocity field conditioned on the netlist embedding. Starting from Gaussian noise, every macro and cell follows a nearly straight path to its position, so a handful of integration steps is enough."
          />
          <div className="flow-eq reveal">
            <div className="flow-eq-row mono">
              <span className="flow-eq-lhs">x</span>
              <sub>t</sub>
              <span> = (1 − t) · x</span>
              <sub>0</sub>
              <span> + t · x</span>
              <sub>1</sub>
            </div>
            <div className="flow-eq-row mono">
              <span>v</span>
              <sub>θ</sub>
              <span>(x</span>
              <sub>t</sub>
              <span>, t, netlist) ≈ x</span>
              <sub>1</sub>
              <span> − x</span>
              <sub>0</sub>
            </div>
            <ul className="flow-legend">
              <li>
                <span className="flow-swatch is-noise" /> x₀: noise sample
              </li>
              <li>
                <span className="flow-swatch is-target" /> x₁: legal placement
              </li>
              <li>
                <span className="flow-swatch is-path" /> straight-line path
              </li>
            </ul>
          </div>
        </div>

        <div className="flow-demo reveal">
          <div className="flow-canvas-wrap grid-backdrop">
            <canvas ref={canvasRef} className="flow-canvas" role="img" aria-label={`Illustration of flow matching at t = ${t.toFixed(2)}`} />
            <span className="flow-tag mono">illustration</span>
          </div>
          <div className="flow-controls">
            <button
              type="button"
              className="btn btn-secondary btn-sm btn-icon"
              onClick={() => setPlaying((p) => !p)}
              aria-label={playing ? "Pause" : "Play"}
            >
              {playing ? <Icon name="stop" size={12} /> : <Icon name="arrowRight" size={14} />}
            </button>
            <label className="flow-slider">
              <span className="visually-hidden">Time t</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.001}
                value={t}
                onChange={(e) => {
                  setPlaying(false);
                  setT(Number(e.target.value));
                }}
              />
            </label>
            <output className="flow-t mono">t = {t.toFixed(2)}</output>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSeed((s) => s + 1)}>
              <Icon name="dice" size={14} /> Resample x₀
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
