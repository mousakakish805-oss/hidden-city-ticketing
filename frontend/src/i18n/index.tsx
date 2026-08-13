import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { CATALOGS, LANGUAGES, type Lang, type StringKey } from "./strings";

const STORAGE_KEY = "hct.lang";

export type Translate = (key: StringKey, params?: Record<string, string | number>) => string;

interface I18nValue {
  lang: Lang;
  dir: "ltr" | "rtl";
  setLang: (lang: Lang) => void;
  t: Translate;
  /** Locale tag for Intl formatting. */
  locale: string;
}

const I18nContext = createContext<I18nValue | null>(null);

function detectLanguage(): Lang {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "en" || stored === "ar") return stored;
  return navigator.language?.toLowerCase().startsWith("ar") ? "ar" : "en";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => detectLanguage());
  const dir = lang === "ar" ? "rtl" : "ltr";

  // Direction has to live on <html> so it cascades to native widgets
  // (date pickers, select dropdowns, scrollbars), not just our own markup.
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = dir;
  }, [lang, dir]);

  const setLang = useCallback((next: Lang) => {
    localStorage.setItem(STORAGE_KEY, next);
    setLangState(next);
  }, []);

  const t = useCallback<Translate>(
    (key, params) => {
      const template = CATALOGS[lang][key] ?? CATALOGS.en[key] ?? key;
      if (!params) return template;
      return template.replace(/\{(\w+)\}/g, (match, name: string) =>
        name in params ? String(params[name]) : match,
      );
    },
    [lang],
  );

  const value = useMemo<I18nValue>(
    () => ({
      lang,
      dir,
      setLang,
      t,
      // Arabic with Latin digits: travellers compare these prices against
      // airline sites, which show Latin numerals.
      locale: lang === "ar" ? "ar-u-nu-latn" : "en",
    }),
    [lang, dir, setLang, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside <I18nProvider>");
  return value;
}

/** Picks a singular or plural string, e.g. `results.opportunities`. */
export function plural(t: Translate, base: string, count: number): string {
  const key = (count === 1 ? `${base}_one` : `${base}_other`) as StringKey;
  return t(key, { count });
}

/**
 * Formats a flight duration in the active language.
 *
 * Done client-side rather than using the API's `duration_label`, which is
 * English-only: the browser is where the language actually lives.
 */
export function duration(t: Translate, minutes: number | null | undefined): string {
  if (minutes == null) return "--";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return hours
    ? t("duration.hoursMinutes", { h: hours, m: String(rest).padStart(2, "0") })
    : t("duration.minutes", { m: rest });
}

export { LANGUAGES, type Lang };
