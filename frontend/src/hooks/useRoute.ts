import { useCallback, useEffect, useState } from "react";

export type Route = "search" | "results" | "rules";

const ROUTES: Record<string, Route> = {
  "#/": "search",
  "#/results": "results",
  "#/rules": "rules",
};

const PATHS: Record<Route, string> = {
  search: "#/",
  results: "#/results",
  rules: "#/rules",
};

function current(): Route {
  return ROUTES[window.location.hash] ?? "search";
}

/**
 * Three pages, addressed by hash.
 *
 * Hash routing rather than a router library: the website has three views and
 * no nested layouts, so a dependency would be all cost. It still gives real
 * URLs — the back button works, and the rules page can be linked to directly,
 * which matters for a page users are told to go and read.
 */
export function useRoute() {
  const [route, setRouteState] = useState<Route>(() => current());

  useEffect(() => {
    const onChange = () => {
      setRouteState(current());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const navigate = useCallback((next: Route) => {
    if (window.location.hash === PATHS[next]) {
      window.scrollTo(0, 0);
      return;
    }
    window.location.hash = PATHS[next];
  }, []);

  return { route, navigate };
}
