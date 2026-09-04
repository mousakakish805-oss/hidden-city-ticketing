import { useEffect, useState } from "react";

/**
 * A photograph of a real city, fetched by name.
 *
 * Source is Wikipedia's page-summary endpoint, which needs no API key and
 * returns the lead image of the article — so the picture above a Madrid
 * search is actually Madrid, not a stock photograph of somewhere sunny. That
 * matters more here than it would on a travel brochure: this website already
 * had to apologise once for showing a flight that did not exist, and a photo
 * captioned with the wrong city is the same kind of lie in a different medium.
 *
 * Everything about it is best-effort. A city with no article, a redirect, a
 * blocked request or an offline visitor all resolve to `null`, and every
 * caller must render properly without a picture. Nothing here is allowed to
 * make a search fail.
 *
 * Results are memoised for the life of the page: switching language re-runs
 * the search, and Wikipedia should not be asked for Madrid five times.
 */
interface Summary {
  originalimage?: { source?: string; width?: number };
  thumbnail?: { source?: string };
}

/** Widest hero we will ever need; beyond this it is bytes nobody sees. */
const TARGET_WIDTH = 1280;

/**
 * Wikipedia hands back two sizes and neither is usable as-is: `thumbnail` is
 * always 330px wide, which is a blurry smear across a hero, and
 * `originalimage` runs to 6000px and several megabytes.
 *
 * Commons serves any width from the same path, so the thumbnail URL is
 * rewritten to ask for one that fits — capped at the original's own width,
 * because the thumbnailer refuses to upscale and returns an error instead.
 */
function pickImage(data: Summary | null): string | null {
  const thumb = data?.thumbnail?.source;
  const original = data?.originalimage?.source;
  const candidate = thumb ?? original ?? null;
  if (!candidate) return null;

  // SVG lead images are diagrams, flags and coats of arms, never photographs.
  if (/\.svgs?(\?|$)/i.test(candidate)) return null;

  if (!thumb) return original ?? null;

  const width = Math.min(TARGET_WIDTH, data?.originalimage?.width ?? TARGET_WIDTH);
  // ".../thumb/a/ab/Name.jpg/330px-Name.jpg" -> ".../1280px-Name.jpg"
  return thumb.replace(/\/(\d+)px-/, () => `/${width}px-`);
}

const cache = new Map<string, string | null>();

const ENDPOINT = "https://en.wikipedia.org/api/rest_v1/page/summary/";

export function useCityPhoto(city: string | null | undefined): string | null {
  const [url, setUrl] = useState<string | null>(() => (city ? (cache.get(city) ?? null) : null));

  useEffect(() => {
    if (!city) {
      setUrl(null);
      return;
    }
    if (cache.has(city)) {
      setUrl(cache.get(city) ?? null);
      return;
    }

    // A late response must not overwrite a newer city's photo.
    let current = true;
    const controller = new AbortController();

    fetch(ENDPOINT + encodeURIComponent(city), { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((data: Summary | null) => {
        const found = pickImage(data);
        cache.set(city, found);
        if (current) setUrl(found);
      })
      .catch(() => {
        // Offline, blocked, or an aborted request. A page without a photograph
        // is a perfectly good page.
        if (current) setUrl(null);
      });

    return () => {
      current = false;
      controller.abort();
    };
  }, [city]);

  return url;
}
