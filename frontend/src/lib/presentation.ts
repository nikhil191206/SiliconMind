/**
 * Presentation mode: hides the mode strips (Demo mode / Fallback mode) and the
 * connection badge for a live presentation. Turn on with
 * VITE_PRESENTATION_MODE=true in frontend/.env.local, then restart `npm run dev`.
 * Verification banners and "unverified" badges are NOT affected.
 */
export const PRESENTATION_MODE = (import.meta.env.VITE_PRESENTATION_MODE ?? "false").toLowerCase() === "true";
