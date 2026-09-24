/**
 * GLSL for the hero scene.
 *
 * RAINBOW: an unlit "light-sweep" material. A virtual light direction orbits
 * the object over time; each fragment's world normal is compared with it and
 * the result indexes a 5-stop palette (sky → teal → soft yellow → peach →
 * warm red, the same stops as --rainbow in tokens.css). A faint position
 * term keeps large faces from looking flat, and a saturation lift makes the
 * layer read as a luminous core between matte slabs.
 *
 * GRAIN: fullscreen post pass that adds per-pixel film grain, masked by
 * alpha so the transparent background stays perfectly clean.
 */

export const rainbowVertex = /* glsl */ `
  varying vec3 vNormalW;
  varying vec3 vPosL;
  void main() {
    vNormalW = normalize(mat3(modelMatrix) * normal);
    vPosL = position;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

export const rainbowFragment = /* glsl */ `
  precision highp float;
  uniform float uTime;
  uniform float uIntensity;
  varying vec3 vNormalW;
  varying vec3 vPosL;

  vec3 palette(float t) {
    t = clamp(t, 0.0, 1.0);
    vec3 sky    = vec3(0.40, 0.62, 0.94);
    vec3 teal   = vec3(0.50, 0.85, 0.78);
    vec3 yellow = vec3(0.97, 0.93, 0.55);
    vec3 peach  = vec3(0.99, 0.65, 0.36);
    vec3 red    = vec3(0.97, 0.36, 0.42);
    float s = t * 4.0;
    vec3 c = mix(sky, teal, clamp(s, 0.0, 1.0));
    c = mix(c, yellow, clamp(s - 1.0, 0.0, 1.0));
    c = mix(c, peach,  clamp(s - 2.0, 0.0, 1.0));
    c = mix(c, red,    clamp(s - 3.0, 0.0, 1.0));
    return c;
  }

  void main() {
    vec3 n = normalize(vNormalW);

    // Orbiting light with two slow wobbles so the sweep never feels mechanical.
    float a = uTime * 0.30 + sin(uTime * 1.3) * 0.10 + sin(uTime * 0.55 + 1.7) * 0.06;
    vec3 light = normalize(vec3(cos(a), sin(a * 0.7) * 0.55, sin(a)));

    float facing = dot(n, light);
    float t = 0.5 + 0.5 * sin(facing * 1.6 + uTime * 0.55)
            + 0.06 * sin(vPosL.x * 1.2 + vPosL.z * 1.1 + uTime * 0.7);

    vec3 col = palette(t);
    float luma = dot(col, vec3(0.2126, 0.7152, 0.0722));
    col = clamp(luma + (col - luma) * 1.35, 0.0, 1.0) * 1.10;

    // Soft top-light so the layer still reads as a solid.
    col *= mix(0.86, 1.0, clamp(n.y * 0.5 + 0.5, 0.0, 1.0));
    gl_FragColor = vec4(clamp(col * uIntensity, 0.0, 1.0), 1.0);
  }
`;

export const grainVertex = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = vec4(position.xy, 0.0, 1.0);
  }
`;

export const grainFragment = /* glsl */ `
  precision highp float;
  uniform sampler2D uScene;
  uniform float uAmount;
  varying vec2 vUv;
  void main() {
    vec4 src = texture2D(uScene, vUv);
    float n = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453);
    gl_FragColor = vec4(src.rgb + (n - 0.5) * uAmount * src.a, src.a);
  }
`;
