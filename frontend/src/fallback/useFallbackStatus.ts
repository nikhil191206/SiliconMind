/**
 * TEMPORARY DEMO FALLBACK. Asks the live backend whether it is the fallback
 * server. Returns null in Demo mode, against the real backend, or while the
 * request is in flight, so every fallback surface simply doesn't render.
 */
import { useEffect, useState } from "react";
import { useSession } from "../state/SessionProvider";
import { fetchFallbackStatus, type FallbackStatus } from "./fallbackApi";

export function useFallbackStatus(): FallbackStatus | null {
  const { state } = useSession();
  const [status, setStatus] = useState<FallbackStatus | null>(null);

  useEffect(() => {
    if (state.demoMode) {
      setStatus(null);
      return;
    }
    const ctrl = new AbortController();
    fetchFallbackStatus(state.apiBaseUrl, ctrl.signal).then((s) => {
      if (!ctrl.signal.aborted) setStatus(s);
    });
    return () => ctrl.abort();
  }, [state.demoMode, state.apiBaseUrl]);

  return status;
}
