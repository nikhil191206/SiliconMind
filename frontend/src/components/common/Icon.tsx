/**
 * Inline stroke icons (24×24, 2px stroke, round joins: the same visual
 * language as Tabler icons used on rerun.io). Kept local so there's no icon
 * dependency and every glyph is reviewable.
 */
import type { SVGProps } from "react";

const PATHS = {
  arrowRight: "M5 12h14M13 6l6 6-6 6",
  arrowUpRight: "M7 17 17 7M8 7h9v9",
  check: "M5 12l5 5L20 7",
  checkCircle: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8.5 12.5l2.5 2.5 5-5",
  alertTriangle: "M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  alertOctagon:
    "M8.7 3h6.6L21 8.7v6.6L15.3 21H8.7L3 15.3V8.7zM12 8v4M12 16h.01",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 8h.01M11 12h1v4h1",
  x: "M18 6 6 18M6 6l12 12",
  settings:
    "M10.3 4.3c.4-1.8 3-1.8 3.4 0a1.7 1.7 0 0 0 2.6 1.1c1.5-.9 3.3.8 2.4 2.4a1.7 1.7 0 0 0 1 2.5c1.8.4 1.8 3 0 3.4a1.7 1.7 0 0 0-1 2.6c.9 1.5-.9 3.3-2.4 2.4a1.7 1.7 0 0 0-2.6 1c-.4 1.8-3 1.8-3.4 0a1.7 1.7 0 0 0-2.5-1c-1.6.9-3.3-.9-2.4-2.4a1.7 1.7 0 0 0-1.1-2.6c-1.8-.4-1.8-3 0-3.4a1.7 1.7 0 0 0 1.1-2.5c-.9-1.6.8-3.3 2.4-2.4 1 .6 2.3.1 2.5-1.1zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  key: "M16.5 3a4.5 4.5 0 1 1-3.2 7.7L6 18v3H3v-3l7.3-7.3A4.5 4.5 0 0 1 16.5 3zM16.5 7.5h.01",
  eye: "M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  eyeOff: "M3 3l18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.9 5.1A9.8 9.8 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-2.9 3.9M6.6 6.6C3.9 8.4 2 12 2 12s3.6 7 10 7a9.7 9.7 0 0 0 5.4-1.6",
  upload: "M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2M7 9l5-5 5 5M12 4v12",
  file: "M14 3v4a1 1 0 0 0 1 1h4M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z",
  sparkles:
    "M16 18a2 2 0 0 1 2 2 2 2 0 0 1 2-2 2 2 0 0 1-2-2 2 2 0 0 1-2 2zM16 6a2 2 0 0 1 2 2 2 2 0 0 1 2-2 2 2 0 0 1-2-2 2 2 0 0 1-2 2zM9 18a6 6 0 0 1 6-6 6 6 0 0 1-6-6 6 6 0 0 1-6 6 6 6 0 0 1 6 6z",
  copy: "M8 8h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2zM16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2",
  history: "M12 8v4l2 2M3.05 11a9 9 0 1 1 .5 4M3 20v-5h5",
  undo: "M9 14 4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11",
  send: "M10 14 21 3M21 3l-6.5 18a.55.55 0 0 1-1 0L10 14l-7-3.5a.55.55 0 0 1 0-1z",
  refresh: "M20 11A8.1 8.1 0 0 0 4.5 9M4 5v4h4M4 13a8.1 8.1 0 0 0 15.5 2m.5 4v-4h-4",
  cpu: "M5 5h14v14H5zM9 9h6v6H9zM3 10h2M3 14h2M10 3v2M14 3v2M21 10h-2M21 14h-2M14 21v-2M10 21v-2",
  layers: "M12 4 4 8l8 4 8-4-8-4M4 12l8 4 8-4M4 16l8 4 8-4",
  maximize: "M4 8V4h4M20 8V4h-4M4 16v4h4M20 16v4h-4",
  zoomIn: "M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM7 10h6M10 7v6M21 21l-6-6",
  zoomOut: "M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM7 10h6M21 21l-6-6",
  git: "M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12.3 12.3 0 0 0-6.2 0C6.5 2.8 5.4 3.1 5.4 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21",
  terminal: "M5 7l5 5-5 5M12 19h7",
  code: "M7 8l-4 4 4 4M17 8l4 4-4 4M14 4l-4 16",
  flask: "M9 3h6M10 9V3M14 9V3M6.5 21h11a1.5 1.5 0 0 0 1.3-2.2L14 9h-4l-4.8 9.8A1.5 1.5 0 0 0 6.5 21zM7.5 15h9",
  target: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
  message: "M8 9h8M8 13h6M18 4a3 3 0 0 1 3 3v8a3 3 0 0 1-3 3h-5l-5 3v-3H6a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3z",
  chart: "M3 3v18h18M7 15l4-4 3 3 5-6",
  help: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 17h.01M12 13.5a1.5 1.5 0 0 1 1-1.4 2.6 2.6 0 1 0-3.1-3.9",
  list: "M9 6h11M9 12h11M9 18h11M5 6v.01M5 12v.01M5 18v.01",
  search: "M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-6-6",
  network: "M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM12 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 9v1a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V9M12 12v3",
  stop: "M6 6h12v12H6z",
  plus: "M12 5v14M5 12h14",
  chevronDown: "M6 9l6 6 6-6",
  chevronRight: "M9 6l6 6-6 6",
  dice: "M4 4h16v16H4zM8.5 8.5h.01M15.5 8.5h.01M15.5 15.5h.01M8.5 15.5h.01M12 12h.01",
  shield: "M12 3a12 12 0 0 0 8.5 3A12 12 0 0 1 12 21 12 12 0 0 1 3.5 6 12 12 0 0 0 12 3zM9 12l2 2 4-4",
} as const;

export type IconName = keyof typeof PATHS;

interface IconProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: IconName;
  size?: number;
  /** When set, the icon is announced; otherwise it's decorative. */
  label?: string;
}

export function Icon({ name, size = 16, label, ...rest }: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
      style={{ flex: "none" }}
      {...rest}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
