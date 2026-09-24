/**
 * Thin, failure-tolerant wrapper over localStorage.
 *
 * Holds only per-browser preferences (persona, demo settings) and the user's
 * own LLM API key (spec §3.3: BYOK, stored only in this browser, never logged).
 * Private windows / blocked storage throw, every access is guarded so the app
 * still works, it just won't remember.
 */
const PREFIX = "siliconmind:";

export function readStored<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function writeStored<T>(key: string, value: T): void {
  try {
    if (value === null || value === undefined) window.localStorage.removeItem(PREFIX + key);
    else window.localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    /* storage unavailable, preference simply isn't persisted */
  }
}

export const STORAGE_KEYS = {
  persona: "persona",
  apiKey: "apiKey",
  demoMode: "demoMode",
  demoScenario: "demoScenario",
  apiBaseUrl: "apiBaseUrl",
} as const;
