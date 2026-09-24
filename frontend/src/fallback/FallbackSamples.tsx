/**
 * TEMPORARY DEMO FALLBACK. Sample designs served by the fallback server
 * (GET /api/fallback/samples), shown on the intake screen outside Demo mode
 * so the live demo can skip intake with one click.
 */
import { useEffect, useRef, useState } from "react";
import { Icon } from "../components/common/Icon";
import { useSession } from "../state/SessionProvider";
import { fetchFallbackSample, fetchFallbackSamples, type FallbackSample } from "./fallbackApi";
import { useFallbackStatus } from "./useFallbackStatus";
import { PRESENTATION_MODE } from "../lib/presentation";
import "./fallback.css";

export function FallbackSamples({ disabled }: { disabled: boolean }) {
  const { state, actions } = useSession();
  const status = useFallbackStatus();
  const [samples, setSamples] = useState<FallbackSample[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const autoLoaded = useRef(false);

  useEffect(() => {
    if (!status) return;
    fetchFallbackSamples(state.apiBaseUrl).then(setSamples, (e: Error) => setError(e.message));
  }, [status, state.apiBaseUrl]);

  // Demo link: /app?backend=live&sample=small loads a sample and generates right away.
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("sample");
    if (!status || !id || autoLoaded.current || !samples.some((s) => s.id === id)) return;
    autoLoaded.current = true;
    void load(id).then(() => window.setTimeout(() => void actions.generate(), 0));
  }, [status, samples]);

  if (!status) return null;

  async function load(id: string) {
    setBusy(id);
    setError(null);
    try {
      actions.loadGraph(await fetchFallbackSample(state.apiBaseUrl, id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="intake-samples" aria-labelledby="fb-samples-title">
      <div className="row">
        <h2 id="fb-samples-title" className="caption">
          Sample designs
        </h2>
        {!PRESENTATION_MODE && <span className="badge badge-warn">fallback server</span>}
      </div>
      <div className="intake-sample-grid">
        {samples.map((s) => (
          <button
            key={s.id}
            type="button"
            className="intake-sample"
            onClick={() => load(s.id)}
            disabled={disabled || busy !== null}
          >
            <span className="mono">{s.label}</span>
            <span className="hint">{s.description}</span>
            {busy === s.id && <span className="spinner intake-sample-spin" />}
          </button>
        ))}
      </div>
      {error && (
        <p className="hint fb-bad" role="alert">
          <Icon name="info" size={12} /> {error}
        </p>
      )}
      <p className="hint">
        Served by the fallback backend. <span className="mono">mock_toy_design</span> is the exact{" "}
        <span className="mono">shared/mocks</span> fixture; the others are synthetic clustered netlists, not real
        benchmark chips.
      </p>
    </section>
  );
}
