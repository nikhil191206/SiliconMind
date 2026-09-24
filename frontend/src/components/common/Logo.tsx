/**
 * SiliconMind wordmark: a three-layer isometric glyph (two neutral layers +
 * one rainbow layer, echoing the hero's slab stack) and the name set in the
 * system sans at 550.
 */
import { useId } from "react";
import "./Logo.css";

export function LogoGlyph({ size = 22 }: { size?: number }) {
  const gid = useId().replace(/:/g, "");
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={`rb-${gid}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#669ef0" />
          <stop offset=".25" stopColor="#80d9c7" />
          <stop offset=".5" stopColor="#f7ed8c" />
          <stop offset=".75" stopColor="#fca65c" />
          <stop offset="1" stopColor="#f75c6b" />
        </linearGradient>
      </defs>
      <path d="M3 7.2 12 3l9 4.2-9 4.2z" fill="#0a0a0a" />
      <path d="M3 12 12 7.8l9 4.2-9 4.2z" fill="#737373" opacity=".85" />
      <path d="M3 16.8 12 12.6l9 4.2-9 4.2z" fill={`url(#rb-${gid})`} />
    </svg>
  );
}

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className="logo">
      <LogoGlyph />
      {!compact && <span className="logo-word">SiliconMind</span>}
    </span>
  );
}
