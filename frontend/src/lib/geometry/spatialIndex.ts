/**
 * Uniform-grid spatial index over placed node bounding boxes.
 *
 * Built once per (graph, placement) pair, then queried every frame so the
 * canvas only touches nodes that intersect the viewport (spec §5.2 viewport
 * culling) and hit-testing a click is O(nodes in one cell), not O(all nodes).
 * Designs in this project go up to 925,010 nodes, so this matters.
 */
import type { BBox } from "./geometry";

export class SpatialIndex {
  readonly cols: number;
  readonly rows: number;
  readonly cellW: number;
  readonly cellH: number;
  private readonly originX: number;
  private readonly originY: number;
  private readonly cells: Int32Array[];

  /**
   * @param boxes flat [x0,y0,x1,y1, ...] per item (item index = position / 4)
   * @param bounds region to grid over (normally the die, grown to include
   *               anything placed outside it so out-of-die nodes stay findable)
   */
  constructor(boxes: Float64Array, bounds: BBox, targetPerCell = 24) {
    const n = boxes.length / 4;
    const w = Math.max(bounds.x1 - bounds.x0, 1e-9);
    const h = Math.max(bounds.y1 - bounds.y0, 1e-9);
    const totalCells = Math.max(1, Math.min(262_144, Math.ceil(n / targetPerCell)));
    const aspect = w / h;
    this.cols = Math.max(1, Math.round(Math.sqrt(totalCells * aspect)));
    this.rows = Math.max(1, Math.round(totalCells / this.cols));
    this.cellW = w / this.cols;
    this.cellH = h / this.rows;
    this.originX = bounds.x0;
    this.originY = bounds.y0;

    // Two-pass bucket fill (count, then place) keeps memory flat for huge n.
    const counts = new Int32Array(this.cols * this.rows);
    this.forEachCell(boxes, n, (_i, c) => {
      counts[c]++;
    });
    this.cells = Array.from(counts, (c) => new Int32Array(c));
    const fill = new Int32Array(this.cols * this.rows);
    this.forEachCell(boxes, n, (i, c) => {
      this.cells[c][fill[c]++] = i;
    });
  }

  private clampCol(x: number): number {
    return Math.min(this.cols - 1, Math.max(0, Math.floor((x - this.originX) / this.cellW)));
  }

  private clampRow(y: number): number {
    return Math.min(this.rows - 1, Math.max(0, Math.floor((y - this.originY) / this.cellH)));
  }

  private forEachCell(boxes: Float64Array, n: number, fn: (i: number, cell: number) => void): void {
    for (let i = 0; i < n; i++) {
      const c0 = this.clampCol(boxes[i * 4]);
      const c1 = this.clampCol(boxes[i * 4 + 2]);
      const r0 = this.clampRow(boxes[i * 4 + 1]);
      const r1 = this.clampRow(boxes[i * 4 + 3]);
      for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) fn(i, r * this.cols + c);
    }
  }

  /** Calls fn once per item whose cell range intersects the query box (may include near-misses). */
  query(q: BBox, fn: (i: number) => void, seen: Uint8Array): void {
    const c0 = this.clampCol(q.x0);
    const c1 = this.clampCol(q.x1);
    const r0 = this.clampRow(q.y0);
    const r1 = this.clampRow(q.y1);
    const touched: number[] = [];
    for (let r = r0; r <= r1; r++) {
      for (let c = c0; c <= c1; c++) {
        const cell = this.cells[r * this.cols + c];
        for (let k = 0; k < cell.length; k++) {
          const i = cell[k];
          if (seen[i]) continue;
          seen[i] = 1;
          touched.push(i);
          fn(i);
        }
      }
    }
    for (const i of touched) seen[i] = 0;
  }
}
