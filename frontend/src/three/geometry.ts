/**
 * Geometry builders: a beveled rounded-rectangle slab (the die layers) and a
 * small rounded block (macros). Both are centred on the origin with Y up, so
 * a slab of thickness `t` spans y ∈ [−t/2, +t/2].
 */
import * as THREE from "three";

function roundedRectShape(w: number, h: number, r: number): THREE.Shape {
  const s = new THREE.Shape();
  const x = -w / 2;
  const y = -h / 2;
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y);
  s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r);
  s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h);
  s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r);
  s.quadraticCurveTo(x, y, x + r, y);
  return s;
}

/**
 * @param size      footprint edge length (square)
 * @param thickness total height including bevels
 * @param radius    corner radius of the footprint
 * @param bevel     bevel size on the top/bottom edges
 */
export function createSlabGeometry(size = 4, thickness = 0.35, radius = 0.42, bevel = 0.05): THREE.BufferGeometry {
  const inner = size - 2 * bevel;
  const shape = roundedRectShape(inner, inner, Math.max(0.001, radius - bevel));
  const geo = new THREE.ExtrudeGeometry(shape, {
    depth: thickness - 2 * bevel,
    bevelEnabled: true,
    bevelThickness: bevel,
    bevelSize: bevel,
    bevelSegments: 4,
    curveSegments: 16,
  });
  geo.translate(0, 0, -thickness / 2 + bevel);
  geo.rotateX(-Math.PI / 2);
  geo.computeVertexNormals();
  return geo;
}

/** Unit-footprint rounded block (1 × h × 1); scale x/z per macro. */
export function createBlockGeometry(height = 0.14): THREE.BufferGeometry {
  const bevel = 0.02;
  const shape = roundedRectShape(1 - 2 * bevel, 1 - 2 * bevel, 0.06);
  const geo = new THREE.ExtrudeGeometry(shape, {
    depth: height - 2 * bevel,
    bevelEnabled: true,
    bevelThickness: bevel,
    bevelSize: bevel,
    bevelSegments: 2,
    curveSegments: 6,
  });
  geo.translate(0, 0, bevel);
  geo.rotateX(-Math.PI / 2);
  // Now spans y ∈ [0, height]: sits ON a surface when placed at its y.
  geo.computeVertexNormals();
  return geo;
}
