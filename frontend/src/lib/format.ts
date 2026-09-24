/** Number/text formatting helpers. Formatting only: never invents values. */

const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const grouped = new Intl.NumberFormat("en-US");

export function formatInt(n: number): string {
  return grouped.format(Math.round(n));
}

export function formatCompact(n: number): string {
  return compact.format(n);
}

export function formatNumber(n: number, digits = 2): string {
  if (!Number.isFinite(n)) return String(n);
  const abs = Math.abs(n);
  if (abs !== 0 && (abs >= 1e7 || abs < 1e-3)) return n.toExponential(2);
  return n.toLocaleString("en-US", { maximumFractionDigits: digits });
}

export function formatSeconds(s: number): string {
  if (s < 0.01) return `${(s * 1000).toFixed(2)} ms`;
  if (s < 1) return `${(s * 1000).toFixed(0)} ms`;
  if (s < 60) return `${s.toFixed(2)} s`;
  const m = Math.floor(s / 60);
  return `${m}m ${Math.round(s - m * 60)}s`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function formatSigned(n: number, digits = 2): string {
  const s = formatNumber(Math.abs(n), digits);
  if (n > 0) return `+${s}`;
  if (n < 0) return `−${s}`;
  return `±${s}`;
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function pluralize(n: number, one: string, many = one + "s"): string {
  return `${formatInt(n)} ${n === 1 ? one : many}`;
}
