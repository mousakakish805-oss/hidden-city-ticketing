import { useEffect, useRef, useState } from "react";

/**
 * The world-map animation, as the page's background.
 *
 * Everything about how this loads is shaped by one fact: it is decoration
 * that weighs more than the entire application. The animation is 739KB of
 * JSON (166KB over the wire) and the player another ~50KB, against a site
 * that currently ships 81KB in total. Paid up front, that is a slower first
 * paint for every visitor in exchange for something behind the text.
 *
 * So nothing here is on the critical path:
 *
 * * The player arrives by dynamic `import()`, which Vite splits into its own
 *   chunk, requested only when this component mounts.
 * * The animation is fetched from `public/` rather than imported, so it never
 *   enters the JS bundle and the browser can cache it on its own.
 * * Both are deferred to an idle callback, so they queue behind the search
 *   form, the fonts and the destination photograph.
 * * It fades in when ready. Until then the page looks exactly as it did
 *   before, and if either request fails it stays that way for good.
 *
 * Under `prefers-reduced-motion` the map still renders -- it is a map, and a
 * still one is perfectly nice -- but it is frozen on a single frame.
 */

const ANIMATION_URL = "/world-map.json";

/**
 * One fetch per page, however many times the effect runs.
 *
 * React's StrictMode invokes effects twice in development, and hot reloads
 * remount on top of that -- three requests for a 739KB file were observed
 * before this existed. Caching the *promise* rather than the result also
 * collapses concurrent callers into the single request already in flight.
 */
let animationData: Promise<unknown> | null = null;

function loadAnimationData(): Promise<unknown> {
  if (!animationData) {
    animationData = fetch(ANIMATION_URL).then((response) => {
      if (!response.ok) {
        // Do not cache a failure; a later mount deserves a fresh attempt.
        animationData = null;
        throw new Error(`world map: HTTP ${response.status}`);
      }
      return response.json();
    });
  }
  return animationData;
}

export function WorldMapBackdrop() {
  const host = useRef<HTMLDivElement | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // `unknown` rather than the library's type: importing the type eagerly
    // would defeat the point of importing the library lazily.
    let animation: { destroy: () => void; goToAndStop: (f: number, isFrame: boolean) => void } | null =
      null;

    const load = async () => {
      const container = host.current;
      if (!container) return;

      try {
        // The light build drops expression support, which this file does not
        // use, and is roughly a third smaller for it.
        const [{ default: lottie }, data] = await Promise.all([
          import("lottie-web/build/player/lottie_light"),
          loadAnimationData(),
        ]);
        if (cancelled || !host.current) return;

        const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        animation = lottie.loadAnimation({
          container,
          renderer: "svg",
          loop: true,
          autoplay: !reduced,
          animationData: data,
          rendererSettings: {
            // Fill the viewport the way a background image would, rather than
            // letterboxing a 16:9 canvas into a taller page.
            preserveAspectRatio: "xMidYMid slice",
            progressiveLoad: true,
          },
        });
        if (reduced) animation.goToAndStop(0, true);
        setReady(true);
      } catch {
        // Offline, blocked, or a chunk that failed to load. The page has a
        // background already; it simply stays plain.
      }
    };

    // Queue behind everything the visitor actually came for.
    const idle = window.requestIdleCallback
      ? window.requestIdleCallback(() => void load(), { timeout: 2500 })
      : window.setTimeout(() => void load(), 1200);

    return () => {
      cancelled = true;
      if (window.cancelIdleCallback) window.cancelIdleCallback(idle as number);
      else window.clearTimeout(idle as number);
      animation?.destroy();
    };
  }, []);

  return (
    <div
      ref={host}
      aria-hidden
      className={`world-map ${ready ? "world-map-ready" : ""}`}
      data-testid="world-map"
    />
  );
}
