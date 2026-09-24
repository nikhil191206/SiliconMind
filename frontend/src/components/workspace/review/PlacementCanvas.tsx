/**
 * PlacementCanvas: FRONTEND_SPEC.md §5.
 *
 * Interaction:
 *   drag              pan
 *   wheel / pinch     zoom around the cursor
 *   click             select a macro (or a cell when zoomed in)
 *   shift+click       add/remove from selection
 *   shift+drag        box-select macros
 *   keyboard (focus the canvas): arrows pan · + / − zoom · 0 fit die ·
 *                     Esc clear selection
 * A keyboard-only equivalent for selection lives in MacroList (§10).
 *
 * Redraws are on demand (rAF when something changed), not a busy loop.
 */
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import type { CircuitGraph, DiffReport, PlacementJSON } from "../../../lib/schemas";
import { preparePlacement } from "./canvas/prepare";
import { boxSelect, hitTest, renderPlacement, type DiffOverlay, type RenderStats } from "./canvas/renderer";
import { fitScale, fitView, toScreenX, toScreenY, toWorld, zoomAt, type View } from "./canvas/viewport";
import "./PlacementCanvas.css";

export interface PlacementCanvasHandle {
  fit(): void;
  zoomBy(factor: number): void;
  focusNode(id: number): void;
}

interface PlacementCanvasProps {
  circuitGraph: CircuitGraph;
  placement: PlacementJSON;
  /** When set, draws ghosts + arrows from these positions (diff view). */
  previousPlacement: PlacementJSON | null;
  diffReport: DiffReport | null;
  showNets: boolean;
  showLabels: boolean;
  selection: number[];
  onSelect(ids: number[], mode: "replace" | "toggle" | "add"): void;
  onHover?(id: number | null): void;
  onStats?(stats: RenderStats & { zoom: number }): void;
}

export const PlacementCanvas = forwardRef<PlacementCanvasHandle, PlacementCanvasProps>(function PlacementCanvas(
  { circuitGraph, placement, previousPlacement, diffReport, showNets, showLabels, selection, onSelect, onHover, onStats },
  ref,
) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const viewRef = useRef<View | null>(null);
  const baseScaleRef = useRef(1);
  const rafRef = useRef(0);
  const dragRef = useRef<{ sx: number; sy: number; cx: number; cy: number; moved: boolean; box: boolean } | null>(null);
  const [marquee, setMarquee] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [cursor, setCursor] = useState<"grab" | "grabbing" | "crosshair" | "pointer">("grab");

  const prepared = useMemo(() => preparePlacement(circuitGraph, placement), [circuitGraph, placement]);
  const previousPrepared = useMemo(
    () => (previousPlacement ? preparePlacement(circuitGraph, previousPlacement) : null),
    [circuitGraph, previousPlacement],
  );
  const diff: DiffOverlay | null = useMemo(() => {
    if (!previousPrepared || !diffReport) return null;
    return {
      previous: previousPrepared,
      moved: new Set(diffReport.moved_nodes.map((m) => m.node_id)),
      unexpected: new Set(diffReport.unexpected_moves),
    };
  }, [previousPrepared, diffReport]);
  const selectionSet = useMemo(() => new Set(selection), [selection]);

  // Keep latest render inputs in a ref so the rAF callback is stable.
  const inputs = useRef({ prepared, diff, selectionSet, hovered, showNets, showLabels, marquee, circuitGraph, onStats });
  inputs.current = { prepared, diff, selectionSet, hovered, showNets, showLabels, marquee, circuitGraph, onStats };

  const draw = useCallback(() => {
    rafRef.current = 0;
    const canvas = canvasRef.current;
    const v = viewRef.current;
    if (!canvas || !v) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const i = inputs.current;
    const stats = renderPlacement(ctx, v, i.prepared, {
      graph: i.circuitGraph,
      selection: i.selectionSet,
      hovered: i.hovered,
      showNets: i.showNets,
      showLabels: i.showLabels,
      diff: i.diff,
      marquee: i.marquee,
    });
    i.onStats?.({ ...stats, zoom: v.scale / baseScaleRef.current });
  }, []);

  const requestDraw = useCallback(() => {
    if (!rafRef.current) rafRef.current = requestAnimationFrame(draw);
  }, [draw]);

  // Size canvas to its container (and to DPR).
  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return;
    const resize = () => {
      const w = wrap.clientWidth;
      const h = wrap.clientHeight;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      const die = inputs.current.prepared.die;
      baseScaleRef.current = fitScale(die, w, h);
      viewRef.current = viewRef.current ? { ...viewRef.current, width: w, height: h } : fitView(die, w, h);
      requestDraw();
    };
    // Size immediately (don't wait for the first observer callback), then track changes.
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(wrap);
    return () => ro.disconnect();
  }, [requestDraw]);

  // New design → refit to the die. New placement of the same design → keep the view.
  const lastDesign = useRef<string | null>(null);
  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const key = `${circuitGraph.design_name}:${circuitGraph.die.width}x${circuitGraph.die.height}:${circuitGraph.nodes.length}`;
    if (lastDesign.current !== key) {
      lastDesign.current = key;
      baseScaleRef.current = fitScale(prepared.die, wrap.clientWidth, wrap.clientHeight);
      viewRef.current = fitView(prepared.die, wrap.clientWidth, wrap.clientHeight);
    }
    requestDraw();
  }, [circuitGraph, prepared, requestDraw]);

  useEffect(() => {
    requestDraw();
  }, [diff, selectionSet, hovered, showNets, showLabels, marquee, requestDraw]);

  useEffect(
    () => () => {
      // Reset the id too: StrictMode re-mounts effects, and a stale id would
      // make every later requestDraw() think a frame is already queued.
      cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    },
    [],
  );

  useImperativeHandle(
    ref,
    () => ({
      fit() {
        const v = viewRef.current;
        if (!v) return;
        viewRef.current = fitView(prepared.die, v.width, v.height);
        requestDraw();
      },
      zoomBy(factor: number) {
        const v = viewRef.current;
        if (!v) return;
        viewRef.current = zoomAt(v, v.width / 2, v.height / 2, factor, baseScaleRef.current);
        requestDraw();
      },
      focusNode(id: number) {
        const v = viewRef.current;
        if (!v || id < 0 || id >= prepared.n) return;
        const b = prepared.boxes;
        const cx = (b[id * 4] + b[id * 4 + 2]) / 2;
        const cy = (b[id * 4 + 1] + b[id * 4 + 3]) / 2;
        const size = Math.max(b[id * 4 + 2] - b[id * 4], b[id * 4 + 3] - b[id * 4 + 1]);
        const wanted = Math.min(v.width, v.height) / Math.max(size * 4, 1e-9);
        viewRef.current = { ...v, cx, cy, scale: Math.max(v.scale, Math.min(wanted, baseScaleRef.current * 50)) };
        requestDraw();
      },
    }),
    [prepared, requestDraw],
  );

  // ---- Pointer ------------------------------------------------------------

  function local(e: React.PointerEvent | React.WheelEvent): [number, number] {
    const r = canvasRef.current!.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }

  function onPointerDown(e: React.PointerEvent<HTMLCanvasElement>) {
    if (e.button !== 0) return;
    const v = viewRef.current;
    if (!v) return;
    const [sx, sy] = local(e);
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { sx, sy, cx: v.cx, cy: v.cy, moved: false, box: e.shiftKey };
    setCursor(e.shiftKey ? "crosshair" : "grabbing");
  }

  function onPointerMove(e: React.PointerEvent<HTMLCanvasElement>) {
    const v = viewRef.current;
    if (!v) return;
    const [sx, sy] = local(e);
    const d = dragRef.current;
    if (d) {
      if (Math.hypot(sx - d.sx, sy - d.sy) > 3) d.moved = true;
      if (d.box) {
        setMarquee({ x0: d.sx, y0: d.sy, x1: sx, y1: sy });
      } else if (d.moved) {
        viewRef.current = { ...v, cx: d.cx - (sx - d.sx) / v.scale, cy: d.cy + (sy - d.sy) / v.scale };
        requestDraw();
      }
      return;
    }
    const [wx, wy] = toWorld(v, sx, sy);
    const hit = hitTest(v, prepared, wx, wy);
    if (hit !== hovered) {
      setHovered(hit);
      onHover?.(hit);
    }
    setCursor(hit !== null ? "pointer" : "grab");
  }

  function onPointerUp(e: React.PointerEvent<HTMLCanvasElement>) {
    const v = viewRef.current;
    const d = dragRef.current;
    dragRef.current = null;
    setCursor("grab");
    if (!v || !d) return;
    const [sx, sy] = local(e);
    if (d.box && d.moved) {
      const [ax, ay] = toWorld(v, d.sx, d.sy);
      const [bx, by] = toWorld(v, sx, sy);
      onSelect(boxSelect(prepared, ax, ay, bx, by), "add");
      setMarquee(null);
      return;
    }
    setMarquee(null);
    if (d.moved) return;
    const [wx, wy] = toWorld(v, sx, sy);
    const hit = hitTest(v, prepared, wx, wy);
    if (hit === null) {
      if (!e.shiftKey) onSelect([], "replace");
    } else {
      onSelect([hit], e.shiftKey ? "toggle" : "replace");
    }
  }

  // Wheel must be non-passive to preventDefault page scroll.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const v = viewRef.current;
      if (!v) return;
      const r = canvas.getBoundingClientRect();
      const factor = Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015));
      viewRef.current = zoomAt(v, e.clientX - r.left, e.clientY - r.top, factor, baseScaleRef.current);
      requestDraw();
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [requestDraw]);

  function onKeyDown(e: React.KeyboardEvent<HTMLCanvasElement>) {
    const v = viewRef.current;
    if (!v) return;
    const step = 60 / v.scale;
    let handled = true;
    switch (e.key) {
      case "ArrowLeft":
        viewRef.current = { ...v, cx: v.cx - step };
        break;
      case "ArrowRight":
        viewRef.current = { ...v, cx: v.cx + step };
        break;
      case "ArrowUp":
        viewRef.current = { ...v, cy: v.cy + step };
        break;
      case "ArrowDown":
        viewRef.current = { ...v, cy: v.cy - step };
        break;
      case "+":
      case "=":
        viewRef.current = zoomAt(v, v.width / 2, v.height / 2, 1.25, baseScaleRef.current);
        break;
      case "-":
      case "_":
        viewRef.current = zoomAt(v, v.width / 2, v.height / 2, 0.8, baseScaleRef.current);
        break;
      case "0":
        viewRef.current = fitView(prepared.die, v.width, v.height);
        break;
      case "Escape":
        onSelect([], "replace");
        break;
      default:
        handled = false;
    }
    if (handled) {
      e.preventDefault();
      requestDraw();
    }
  }

  // Tooltip for the hovered node.
  const tooltip = useMemo(() => {
    const v = viewRef.current;
    if (hovered === null || !v) return null;
    const node = circuitGraph.nodes[hovered];
    const b = prepared.boxes;
    const x = toScreenX(v, b[hovered * 4 + 2]);
    const y = toScreenY(v, b[hovered * 4 + 3]);
    return { node, x, y, orientation: prepared.orientation[hovered] };
  }, [hovered, prepared, circuitGraph]);

  return (
    <div ref={wrapRef} className="pcanvas">
      <canvas
        ref={canvasRef}
        className="pcanvas-el"
        style={{ cursor }}
        tabIndex={0}
        role="application"
        aria-roledescription="placement canvas"
        aria-label={`Placement of ${circuitGraph.design_name}: ${prepared.macroIds.length} macros and ${prepared.cellIds.length} standard cells on a ${circuitGraph.die.width} × ${circuitGraph.die.height} die. Arrow keys pan, plus and minus zoom, 0 fits the die. Use the macro list to select macros by keyboard.`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => {
          if (!dragRef.current && hovered !== null) {
            setHovered(null);
            onHover?.(null);
          }
        }}
        onKeyDown={onKeyDown}
      />
      {tooltip && !dragRef.current && (
        <div
          className="pcanvas-tip mono"
          style={{ left: Math.min(tooltip.x + 8, (viewRef.current?.width ?? 0) - 170), top: Math.max(tooltip.y - 8, 8) }}
          role="presentation"
        >
          <strong>
            {tooltip.node.type === "MACRO" ? "Macro" : "Cell"} {tooltip.node.node_id}
          </strong>
          <span>
            {tooltip.node.width}×{tooltip.node.height} · {tooltip.orientation} · {tooltip.node.pin_count} pins
          </span>
        </div>
      )}
      {prepared.outOfDie.length > 0 && (
        <p className="pcanvas-flag" role="status">
          ⚠ {prepared.outOfDie.length} node(s) placed outside the die boundary (outlined in red)
        </p>
      )}
      {prepared.missing > 0 && (
        <p className="pcanvas-flag" role="status">
          ⚠ {prepared.missing} node(s) in the CircuitGraph have no entry in this placement
        </p>
      )}
    </div>
  );
});
