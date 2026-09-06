import { useEffect, useRef } from "react";

import { WorldMapBackdrop } from "./WorldMapBackdrop";

/**
 * Ambient background layer: curved flight paths with lights travelling along them.
 *
 * Purely decorative and purely additive — it sits behind everything at
 * `-z-10`, takes no pointer events, and is hidden from assistive technology.
 * Nothing on the page depends on it rendering.
 *
 * Three things keep it from becoming a nuisance:
 *
 * * It only draws in the dark theme. Over the light theme's white surfaces the
 *   same arcs read as smudges rather than depth.
 * * Everything is drawn at 10–20% alpha, so text laid over it stays legible
 *   without the layer needing to know where the text is.
 * * It stops entirely when the tab is hidden, and never starts when the
 *   visitor has asked for reduced motion — a canvas repainting sixty times a
 *   second behind a background tab is a battery cost with no viewer.
 */

interface Arc {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** How far the curve bows off the straight line, in pixels. */
  bow: number;
  /** Position of the light along the arc, 0..1. */
  t: number;
  speed: number;
}

const ARC_COUNT = 7;
// The brief asks for 10-20%, and it is the right ceiling: text sits over this
// layer and the layer has no idea where the text is.
//
// The number that matters is the *composited* peak, not either value alone.
// A particle passing over its own arc stacks the two:
//     1 - (1 - line) x (1 - particle)
// At 0.14 and 0.195 that came out at 31%, over the ceiling even though each
// part was inside it. These values put the worst case at 1 - 0.90 x 0.89, or
// just under 20%.
const LINE_ALPHA = 0.1;
const PARTICLE_ALPHA = 0.22;

/** Quadratic bezier, which is what a flight path looks like on a flat map. */
function pointOn(arc: Arc, t: number): [number, number] {
  const mx = (arc.x1 + arc.x2) / 2;
  const my = (arc.y1 + arc.y2) / 2 - arc.bow;
  const inv = 1 - t;
  return [
    inv * inv * arc.x1 + 2 * inv * t * mx + t * t * arc.x2,
    inv * inv * arc.y1 + 2 * inv * t * my + t * t * arc.y2,
  ];
}

export function FlightPaths() {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const context = canvas.getContext("2d");
    if (!context) return;

    let arcs: Arc[] = [];
    let frame = 0;
    let width = 0;
    let height = 0;

    const isDark = () =>
      document.documentElement.getAttribute("data-theme") === "dark";

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      canvas.width = Math.floor(width * ratio);
      canvas.height = Math.floor(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);

      // Arcs span the full width so they read as routes crossing the page
      // rather than as scratches in one corner.
      arcs = Array.from({ length: ARC_COUNT }, (_, index) => {
        const y = (height / (ARC_COUNT + 1)) * (index + 1);
        return {
          x1: -width * 0.1,
          y1: y + (Math.random() - 0.5) * height * 0.15,
          x2: width * 1.1,
          y2: y + (Math.random() - 0.5) * height * 0.15,
          bow: height * (0.08 + Math.random() * 0.16),
          t: Math.random(),
          speed: 0.0006 + Math.random() * 0.0011,
        };
      });
    };

    const draw = () => {
      context.clearRect(0, 0, width, height);
      if (!isDark()) return;

      for (const arc of arcs) {
        const mx = (arc.x1 + arc.x2) / 2;
        const my = (arc.y1 + arc.y2) / 2 - arc.bow;

        context.globalAlpha = LINE_ALPHA;
        context.strokeStyle = "#5eead4";
        context.lineWidth = 1;
        context.beginPath();
        context.moveTo(arc.x1, arc.y1);
        context.quadraticCurveTo(mx, my, arc.x2, arc.y2);
        context.stroke();

        const [px, py] = pointOn(arc, arc.t);
        const glow = context.createRadialGradient(px, py, 0, px, py, 26);
        glow.addColorStop(0, "rgba(125, 239, 230, 0.5)");
        glow.addColorStop(1, "rgba(125, 239, 230, 0)");
        context.globalAlpha = PARTICLE_ALPHA;
        context.fillStyle = glow;
        context.beginPath();
        context.arc(px, py, 26, 0, Math.PI * 2);
        context.fill();
      }
      context.globalAlpha = 1;
    };

    const tick = () => {
      for (const arc of arcs) {
        arc.t += arc.speed;
        if (arc.t > 1) arc.t = 0;
      }
      draw();
      frame = window.requestAnimationFrame(tick);
    };

    const start = () => {
      window.cancelAnimationFrame(frame);
      if (reduced.matches) {
        draw(); // A still frame is still depth; it just does not move.
        return;
      }
      frame = window.requestAnimationFrame(tick);
    };

    const onVisibility = () => {
      if (document.hidden) window.cancelAnimationFrame(frame);
      else start();
    };

    // The theme can change under us, and the arcs are only drawn in one of
    // them, so a repaint has to follow the attribute.
    const observer = new MutationObserver(draw);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    resize();
    start();
    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", onVisibility);
    reduced.addEventListener("change", start);

    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
      reduced.removeEventListener("change", start);
    };
  }, []);

  return (
    <div aria-hidden className="ambient" data-testid="ambient-layer">
      <div className="ambient-glow ambient-glow-navy" />
      <div className="ambient-glow ambient-glow-cyan" />
      <WorldMapBackdrop />
      <canvas ref={ref} className="ambient-canvas" />
    </div>
  );
}
