/**
 * Card that tilts in 3D toward the pointer, with a rainbow glare that follows
 * the cursor. Pure CSS transforms driven by two custom properties; disabled
 * for touch and reduced-motion users.
 */
import { useRef, type ReactNode } from "react";
import "./TiltCard.css";

interface TiltCardProps {
  children: ReactNode;
  className?: string;
  maxTilt?: number;
}

export function TiltCard({ children, className = "", maxTilt = 7 }: TiltCardProps) {
  const ref = useRef<HTMLDivElement>(null);

  function onMove(e: React.PointerEvent<HTMLDivElement>) {
    if (e.pointerType !== "mouse") return;
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width;
    const py = (e.clientY - r.top) / r.height;
    el.style.setProperty("--rx", `${(0.5 - py) * maxTilt}deg`);
    el.style.setProperty("--ry", `${(px - 0.5) * maxTilt}deg`);
    el.style.setProperty("--gx", `${px * 100}%`);
    el.style.setProperty("--gy", `${py * 100}%`);
    el.classList.add("is-hovered");
  }

  function onLeave() {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty("--rx", "0deg");
    el.style.setProperty("--ry", "0deg");
    el.classList.remove("is-hovered");
  }

  return (
    <div ref={ref} className={`tilt-card ${className}`} onPointerMove={onMove} onPointerLeave={onLeave}>
      <div className="tilt-card-inner">
        {children}
        <span className="tilt-card-glare" aria-hidden="true" />
      </div>
    </div>
  );
}
