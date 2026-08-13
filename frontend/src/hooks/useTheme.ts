import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "hct.theme";

function detect(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") return stored;
  // Follow the operating system until the visitor chooses for themselves.
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/**
 * Light (white/blue) or dark (black/red), persisted per visitor.
 *
 * The attribute lives on <html> rather than a wrapper element so it also
 * reaches native widgets — date pickers, select menus, scrollbars — which are
 * rendered by the browser and never see our React tree.
 */
export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => detect());

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  // Keep following the OS while the visitor has expressed no preference.
  useEffect(() => {
    if (localStorage.getItem(STORAGE_KEY)) return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event: MediaQueryListEvent) =>
      setThemeState(event.matches ? "dark" : "light");
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const setTheme = useCallback((next: Theme) => {
    localStorage.setItem(STORAGE_KEY, next);
    setThemeState(next);
  }, []);

  const toggle = useCallback(
    () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"),
    [setTheme],
  );

  return { theme, setTheme, toggle };
}
