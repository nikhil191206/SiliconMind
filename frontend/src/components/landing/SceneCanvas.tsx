/**
 * React host for a SlabScene. Mounts WebGL lazily, feeds it a scroll-driven
 * "spread" value, and falls back to a static CSS illustration if WebGL is
 * unavailable (old GPUs, some VMs, locked-down browsers).
 */
import { useEffect, useRef, useState } from "react";
import { SlabScene, type SlabSceneOptions } from "../../three/SlabScene";
import "./SceneCanvas.css";

interface SceneCanvasProps extends SlabSceneOptions {
  className?: string;
  /** Map scroll progress through this element to layer separation. */
  scrollSpread?: boolean;
}

function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export function SceneCanvas({ className = "", scrollSpread = false, ...options }: SceneCanvasProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  // Options are read once at mount; the scene is not meant to be reconfigured live.
  const optsRef = useRef(options);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    if (!webglAvailable()) {
      setFailed(true);
      return;
    }
    let scene: SlabScene;
    try {
      scene = new SlabScene(host, optsRef.current);
    } catch {
      setFailed(true);
      return;
    }

    let raf = 0;
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const r = host.getBoundingClientRect();
        const vh = window.innerHeight;
        // 0 while the element sits in its resting position, → 1 as it scrolls up and out.
        const progress = Math.min(1, Math.max(0, -r.top / (r.height * 0.9 || vh)));
        scene.setSpread(progress);
      });
    };
    if (scrollSpread) {
      window.addEventListener("scroll", onScroll, { passive: true });
      onScroll();
    }
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
      scene.dispose();
    };
  }, [scrollSpread]);

  return (
    <div ref={hostRef} className={`scene-canvas ${className}`} aria-hidden="true">
      {failed && (
        <div className="scene-fallback">
          <div className="scene-fallback-slab" />
          <div className="scene-fallback-slab" />
          <div className="scene-fallback-slab is-rainbow" />
        </div>
      )}
    </div>
  );
}
