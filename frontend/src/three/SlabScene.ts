/**
 * SlabScene: the signature 3D object on the landing page.
 *
 * Construction follows rerun.io's hero recipe: three beveled rounded slabs
 * stacked on Y, seen through an orthographic camera from above-front, lit by
 * a prefiltered RoomEnvironment plus a few soft directionals. One slab is
 * painted by the rainbow light-sweep shader; the others are matte clearcoat.
 * Every ROTATE_EVERY seconds each slab turns 90° with an exponential ease-out,
 * staggered per layer, and the frame goes through a film-grain pass.
 *
 * SiliconMind's twist: the top slab is a die. Its macros (rounded blocks)
 * and standard cells (instanced cubes) periodically dissolve into a noise
 * state above the die and then travel along STRAIGHT lines into a new legal
 * layout, the visual story of flow matching (noise → placement along a
 * straight-line probability path).
 *
 * The scene also responds to the pointer (a gentle tilt) and to page scroll
 * (layers separate, "exploded view"). It pauses when off-screen and renders a
 * single still frame under prefers-reduced-motion.
 */
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { createBlockGeometry, createSlabGeometry } from "./geometry";
import { CELL_COUNT, CELL_SIZE, MACRO_SPECS, makeLayout, makeNoise, type Layout } from "./layouts";
import { grainFragment, grainVertex, rainbowFragment, rainbowVertex } from "./shaders";

export type LayerKind = "matte" | "rainbow" | "die";

export interface SlabSceneOptions {
  /** Bottom → top. "die" = matte slab carrying the animated macros/cells. */
  layers: LayerKind[];
  /** Orthographic half-height of the view. */
  frustum?: number;
  /** Vertical distance between layer centres at rest. */
  gap?: number;
  /** Enable the pointer tilt. */
  pointer?: boolean;
  /** Film grain amount (0 disables the post pass). */
  grain?: number;
  /** Vertical offset of the whole stack. */
  offsetY?: number;
}

const ROTATE_EVERY = 5; // s between quarter-turns
const ROTATE_DURATION = 0.9; // s per quarter-turn
const ROTATE_STAGGER = 0.05; // s delay per layer
const FLOW_PERIOD = 10; // s per noise→placement cycle
const LIFT_START = 1.6;
const LIFT_END = 2.4;
const FLOW_END = 4.6;
const SLAB_T = 0.35;

const easeOutExpo = (t: number) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t));
const easeInOutCubic = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const clamp01 = (t: number) => Math.min(1, Math.max(0, t));

export class SlabScene {
  private readonly container: HTMLElement;
  private readonly opts: Required<SlabSceneOptions>;
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100);
  private readonly stack = new THREE.Group();
  private readonly slabs: THREE.Mesh[] = [];
  private readonly disposables: Array<{ dispose(): void }> = [];
  private readonly rainbowUniforms = { uTime: { value: 0 }, uIntensity: { value: 1 } };

  // Post-processing
  private readonly rt: THREE.WebGLRenderTarget;
  private readonly postScene = new THREE.Scene();
  private readonly postCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

  // Die contents
  private dieSlab: THREE.Mesh | null = null;
  private macroMeshes: THREE.Mesh[] = [];
  private cellMesh: THREE.InstancedMesh | null = null;
  private layouts: Layout[] = [];
  private cellDelay: Float32Array = new Float32Array(0);
  private readonly tmpObj = new THREE.Object3D();

  // Runtime
  private time = 0;
  private lastFrame = 0;
  private raf = 0;
  private visible = true;
  private running = false;
  private spread = 0;
  private spreadTarget = 0;
  private pointerX = 0;
  private pointerY = 0;
  private tiltX = 0;
  private tiltY = 0;
  private readonly reducedMotion: boolean;
  private readonly resizeObserver: ResizeObserver;
  private readonly intersectionObserver: IntersectionObserver;

  constructor(container: HTMLElement, options: SlabSceneOptions) {
    this.container = container;
    this.opts = {
      frustum: 2.5,
      gap: 1.0,
      pointer: true,
      grain: 0.06,
      offsetY: 0.3,
      ...options,
    };
    this.reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    this.renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 0.7;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.domElement.style.width = "100%";
    this.renderer.domElement.style.height = "100%";
    this.renderer.domElement.setAttribute("aria-hidden", "true");
    container.appendChild(this.renderer.domElement);

    this.rt = new THREE.WebGLRenderTarget(1, 1, {
      type: THREE.HalfFloatType,
      samples: 4,
      depthBuffer: true,
    });

    this.buildEnvironment();
    this.buildLights();
    this.buildStack();
    this.buildPost();

    this.camera.position.set(0, 3.4, 8.5);
    this.camera.lookAt(0, 0, 0);

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.intersectionObserver = new IntersectionObserver(
      (entries) => {
        for (const e of entries) this.visible = e.isIntersecting;
        if (this.visible) this.start();
      },
      { threshold: 0 },
    );
    this.intersectionObserver.observe(container);

    if (this.opts.pointer) window.addEventListener("pointermove", this.onPointer, { passive: true });
    this.resize();

    if (this.reducedMotion) {
      // A single composed still: mid-rest, die settled.
      this.time = FLOW_PERIOD + 1.2;
      this.update(0);
      this.render();
    } else {
      this.start();
    }
  }

  // ---- Construction ------------------------------------------------------

  private buildEnvironment(): void {
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    const room = new RoomEnvironment();
    const env = pmrem.fromScene(room, 0.04).texture;
    this.scene.environment = env;
    this.disposables.push(env, pmrem);
    room.traverse((o) => {
      const m = o as THREE.Mesh;
      if (m.isMesh) {
        m.geometry.dispose();
        (m.material as THREE.Material).dispose();
      }
    });
  }

  private buildLights(): void {
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x7d8a99, 0.06));
    // Key light casts the soft contact shadows that separate the layers.
    const key = new THREE.DirectionalLight(0xffffff, 0.75);
    key.position.set(2.5, 10, 3.5);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.camera.left = -4;
    key.shadow.camera.right = 4;
    key.shadow.camera.top = 4;
    key.shadow.camera.bottom = -4;
    key.shadow.camera.near = 1;
    key.shadow.camera.far = 20;
    key.shadow.bias = -0.0004;
    key.shadow.normalBias = 0.02;
    key.shadow.radius = 6;
    const rim = new THREE.DirectionalLight(0x9ec1ff, 0.35);
    rim.position.set(-6, 4, -7);
    const fill = new THREE.DirectionalLight(0xffffff, 0.12);
    fill.position.set(2, 3, 8);
    this.scene.add(key, rim, fill);
  }

  private matte(color: number, roughness = 0.65): THREE.MeshPhysicalMaterial {
    const m = new THREE.MeshPhysicalMaterial({
      color,
      roughness,
      metalness: 0,
      clearcoat: 0.4,
      clearcoatRoughness: 0.4,
      envMapIntensity: 0.4,
    });
    this.disposables.push(m);
    return m;
  }

  private rainbow(): THREE.ShaderMaterial {
    const m = new THREE.ShaderMaterial({
      uniforms: this.rainbowUniforms,
      vertexShader: rainbowVertex,
      fragmentShader: rainbowFragment,
    });
    this.disposables.push(m);
    return m;
  }

  private buildStack(): void {
    const slabGeo = createSlabGeometry(4, SLAB_T, 0.42, 0.05);
    this.disposables.push(slabGeo);
    const slabMatte = this.matte(0xc4c3bf);
    const rainbow = this.rainbow();

    this.opts.layers.forEach((kind) => {
      const mesh = new THREE.Mesh(slabGeo, kind === "rainbow" ? rainbow : slabMatte);
      mesh.castShadow = true;
      mesh.receiveShadow = kind !== "rainbow";
      this.slabs.push(mesh);
      this.stack.add(mesh);
      if (kind === "die") {
        this.dieSlab = mesh;
        this.buildDieContents(mesh, rainbow);
      }
    });
    this.stack.rotation.y = Math.PI / 4;
    this.stack.position.y = this.opts.offsetY;
    this.scene.add(this.stack);
    this.layoutLayers();
  }

  private buildDieContents(die: THREE.Mesh, rainbow: THREE.ShaderMaterial): void {
    this.layouts = [101, 202, 303, 404].map(makeLayout);
    const blockGeo = createBlockGeometry(0.14);
    this.disposables.push(blockGeo);
    // Dark macros (like SRAM/IP blocks on a die shot) read clearly on the pale die.
    const macroMat = this.matte(0x2b2b2b, 0.45);

    MACRO_SPECS.forEach((spec, i) => {
      // Macro 0 is "the one you asked to move", it wears the rainbow.
      const mesh = new THREE.Mesh(blockGeo, i === 0 ? rainbow : macroMat);
      mesh.scale.set(spec.w, 1, spec.d);
      mesh.castShadow = true;
      die.add(mesh);
      this.macroMeshes.push(mesh);
    });

    const cellGeo = new THREE.BoxGeometry(CELL_SIZE, CELL_SIZE * 0.9, CELL_SIZE);
    cellGeo.translate(0, (CELL_SIZE * 0.9) / 2, 0);
    this.disposables.push(cellGeo);
    const cellMat = this.matte(0x6f6e6a, 0.7);
    this.cellMesh = new THREE.InstancedMesh(cellGeo, cellMat, CELL_COUNT);
    this.cellMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.cellMesh.castShadow = true;
    die.add(this.cellMesh);

    this.cellDelay = new Float32Array(CELL_COUNT + MACRO_SPECS.length);
    for (let i = 0; i < this.cellDelay.length; i++) this.cellDelay[i] = Math.random() * 0.35;
  }

  private buildPost(): void {
    const mat = new THREE.ShaderMaterial({
      uniforms: { uScene: { value: this.rt.texture }, uAmount: { value: this.opts.grain } },
      vertexShader: grainVertex,
      fragmentShader: grainFragment,
      transparent: true,
      depthTest: false,
      depthWrite: false,
    });
    const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), mat);
    quad.frustumCulled = false;
    this.postScene.add(quad);
    this.disposables.push(mat, quad.geometry, this.rt);
  }

  // ---- Layout & animation -----------------------------------------------

  private layoutLayers(): void {
    const n = this.slabs.length;
    const gap = this.opts.gap + this.spread * 0.75;
    this.slabs.forEach((s, i) => {
      s.position.y = (i - (n - 1) / 2) * gap;
    });
  }

  private rotationFor(layer: number): number {
    const step = Math.floor(this.time / ROTATE_EVERY);
    const local = (this.time - step * ROTATE_EVERY - layer * ROTATE_STAGGER) / ROTATE_DURATION;
    return (step + easeOutExpo(clamp01(local))) * (Math.PI / 2);
  }

  private updateDie(): void {
    if (!this.dieSlab || !this.cellMesh || this.layouts.length === 0) return;
    const cycle = Math.floor(this.time / FLOW_PERIOD);
    const p = this.time - cycle * FLOW_PERIOD;
    const from = this.layouts[cycle % this.layouts.length];
    const to = this.layouts[(cycle + 1) % this.layouts.length];
    const noise = makeNoiseCached(cycle, CELL_COUNT + MACRO_SPECS.length);
    const top = SLAB_T / 2;

    const position = (i: number, a: { x: number; z: number }, b: { x: number; z: number }) => {
      const d = this.cellDelay[i];
      const lift = easeInOutCubic(clamp01((p - LIFT_START - d) / (LIFT_END - LIFT_START)));
      const flow = easeInOutCubic(clamp01((p - LIFT_END - d) / (FLOW_END - LIFT_END)));
      const nz = noise[i];
      if (flow <= 0) {
        // settled → noise (dissolve upward)
        return { x: a.x + (nz.x - a.x) * lift, y: top + (nz.y - 0) * lift, z: a.z + (nz.z - a.z) * lift };
      }
      // noise → new placement along a straight line
      return { x: nz.x + (b.x - nz.x) * flow, y: top + nz.y * (1 - flow), z: nz.z + (b.z - nz.z) * flow };
    };

    this.macroMeshes.forEach((mesh, i) => {
      const pos = position(CELL_COUNT + i, from.macros[i], to.macros[i]);
      mesh.position.set(pos.x, pos.y, pos.z);
      // A little tumble while airborne; flat when placed.
      const air = clamp01((pos.y - top) / 0.4);
      mesh.rotation.set(air * 0.35 * Math.sin(i + this.time), 0, air * 0.3 * Math.cos(i * 1.7 + this.time));
    });

    for (let i = 0; i < CELL_COUNT; i++) {
      const pos = position(i, from.cells[i], to.cells[i]);
      this.tmpObj.position.set(pos.x, pos.y, pos.z);
      const air = clamp01((pos.y - top) / 0.4);
      this.tmpObj.rotation.set(air * Math.sin(i * 3.1 + this.time * 2), air * i, 0);
      this.tmpObj.updateMatrix();
      this.cellMesh.setMatrixAt(i, this.tmpObj.matrix);
    }
    this.cellMesh.instanceMatrix.needsUpdate = true;
  }

  private update(dt: number): void {
    this.time += dt;
    this.rainbowUniforms.uTime.value = this.time;

    this.slabs.forEach((s, i) => {
      s.rotation.y = this.rotationFor(i);
    });

    // Smooth scroll-driven explode + pointer tilt.
    const k = 1 - Math.pow(0.001, dt);
    this.spread += (this.spreadTarget - this.spread) * k;
    this.tiltX += (this.pointerY * 0.08 - this.tiltX) * k;
    this.tiltY += (this.pointerX * 0.12 - this.tiltY) * k;
    this.stack.rotation.x = this.tiltX;
    this.stack.rotation.y = Math.PI / 4 + this.tiltY;
    this.layoutLayers();
    this.updateDie();
  }

  private render(): void {
    this.renderer.setRenderTarget(this.rt);
    this.renderer.clear();
    this.renderer.render(this.scene, this.camera);
    this.renderer.setRenderTarget(null);
    this.renderer.clear();
    this.renderer.render(this.postScene, this.postCamera);
  }

  private readonly frame = (now: number) => {
    if (!this.running) return;
    const dt = this.lastFrame ? Math.min(0.05, (now - this.lastFrame) / 1000) : 0;
    this.lastFrame = now;
    this.update(dt);
    this.render();
    if (this.visible) this.raf = requestAnimationFrame(this.frame);
    else this.stop();
  };

  private start(): void {
    if (this.running || this.reducedMotion) return;
    this.running = true;
    this.lastFrame = 0;
    this.raf = requestAnimationFrame(this.frame);
  }

  private stop(): void {
    this.running = false;
    cancelAnimationFrame(this.raf);
  }

  private resize(): void {
    const w = Math.max(1, this.container.clientWidth);
    const h = Math.max(1, this.container.clientHeight);
    const aspect = w / h;
    // Keep the rotating stack's diagonal inside the frame on narrow screens.
    const half = Math.max(this.opts.frustum, 3.15 / aspect);
    this.camera.left = -half * aspect;
    this.camera.right = half * aspect;
    this.camera.top = half;
    this.camera.bottom = -half;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h, false);
    const dpr = this.renderer.getPixelRatio();
    this.rt.setSize(Math.round(w * dpr), Math.round(h * dpr));
    if (this.reducedMotion) this.render();
  }

  private readonly onPointer = (e: PointerEvent) => {
    this.pointerX = (e.clientX / window.innerWidth) * 2 - 1;
    this.pointerY = (e.clientY / window.innerHeight) * 2 - 1;
  };

  // ---- Public API --------------------------------------------------------

  /** 0 = resting stack, 1 = fully exploded. Driven by scroll position. */
  setSpread(v: number): void {
    this.spreadTarget = clamp01(v);
    if (this.reducedMotion) {
      this.spread = this.spreadTarget;
      this.layoutLayers();
      this.render();
    }
  }

  dispose(): void {
    this.stop();
    this.resizeObserver.disconnect();
    this.intersectionObserver.disconnect();
    window.removeEventListener("pointermove", this.onPointer);
    for (const d of this.disposables) d.dispose();
    this.cellMesh?.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}

// Noise per cycle is deterministic and reused across frames of that cycle.
const noiseCache = new Map<number, Array<{ x: number; y: number; z: number }>>();
function makeNoiseCached(cycle: number, count: number) {
  let n = noiseCache.get(cycle);
  if (!n) {
    n = makeNoise(9000 + cycle, count);
    noiseCache.set(cycle, n);
    if (noiseCache.size > 4) noiseCache.delete(noiseCache.keys().next().value as number);
  }
  return n;
}
