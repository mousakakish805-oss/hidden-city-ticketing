import { useCallback, useEffect, useRef, useState } from "react";

import { BatchProgress } from "./components/BatchProgress";
import { DisclaimerModal } from "./components/DisclaimerModal";
import { LanguageToggle } from "./components/LanguageToggle";
import { ResultsPanel } from "./components/ResultsPanel";
import { RulesPage } from "./components/RulesPage";
import { SearchForm } from "./components/SearchForm";
import { ThemeToggle } from "./components/ThemeToggle";
import { useDisclaimer } from "./hooks/useDisclaimer";
import { useRoute } from "./hooks/useRoute";
import { useSearch } from "./hooks/useSearch";
import { useTheme } from "./hooks/useTheme";
import { useI18n } from "./i18n";
import { api } from "./lib/api";
import { number } from "./lib/format";
import type { Coverage, Health, SearchParams } from "./types";

export default function App() {
  const { t, lang, locale } = useI18n();
  const { theme, toggle: toggleTheme } = useTheme();
  const { route, navigate } = useRoute();
  const { busy, events, result, error, search } = useSearch();
  const { disclaimer, accepted, open, setOpen, accept } = useDisclaimer(lang);
  const [health, setHealth] = useState<Health | null>(null);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const lastParams = useRef<SearchParams | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => undefined);
    api.coverage().then(setCoverage).catch(() => undefined);
  }, []);

  const runSearch = useCallback(
    (params: SearchParams) => {
      lastParams.current = params;
      search(params);
      // Move to the results page immediately: the batch engine takes tens of
      // seconds, and watching it work is the point of streaming progress.
      navigate("results");
    },
    [search, navigate],
  );

  // Most failures here are worth simply re-running: a quota resets, a dropped
  // connection comes back, a sleeping server wakes. Sending someone back to
  // re-type a route they already typed is the wrong response to "try again
  // later", so the error state offers the retry rather than a blank form.
  const retrySearch = useCallback(() => {
    const previous = lastParams.current;
    if (previous) search({ ...previous, lang });
  }, [search, lang]);

  // Results are rendered server-side, so switching language has to re-run the
  // search. Offers are cached upstream, so this costs no provider API calls.
  useEffect(() => {
    const previous = lastParams.current;
    if (!previous || previous.lang === lang || busy) return;
    const next = { ...previous, lang };
    lastParams.current = next;
    search(next);
  }, [lang, busy, search]);

  // Someone landing on #/results without having searched gets the form, not
  // an empty page.
  useEffect(() => {
    if (route === "results" && !result && !busy && !error) navigate("search");
  }, [route, result, busy, error, navigate]);

  const navItems = [
    { key: "search" as const, label: t("nav.search") },
    { key: "results" as const, label: t("nav.results"), disabled: !result && !busy },
    { key: "rules" as const, label: t("nav.rules") },
  ];

  return (
    <div className="min-h-screen">
      <header className="border-b border-line sticky top-0 bg-canvas/85 backdrop-blur z-20">
        <div className="mx-auto max-w-6xl px-4 pt-3 pb-2 flex items-center gap-4">
          <button
            type="button"
            onClick={() => navigate("search")}
            className="min-w-0 text-start"
          >
            <h1 className="text-lg font-bold tracking-tight">{t("app.title")}</h1>
            <p className="text-xs text-ink-faint truncate">
              {t("app.subtitle")}
              {coverage &&
                ` · ${t("app.coverage", {
                  airports: number(coverage.airports, locale),
                  countries: number(coverage.countries, locale),
                })}`}
            </p>
          </button>

          <div className="ms-auto flex items-center gap-2.5 text-xs shrink-0">
            {health && (
              <span
                title={
                  health.provider_live
                    ? t("header.liveHint", { provider: health.provider })
                    : t("header.syntheticHint")
                }
                className={`px-2 py-1 rounded-full ring-1 ${
                  health.provider_live
                    ? "bg-positive-soft text-positive ring-positive-line"
                    : "bg-warning-soft text-warning ring-warning-line"
                }`}
              >
                {health.provider_live ? t("header.live") : t("header.synthetic")}
              </span>
            )}

            {/* Metered plans only. Seeing the balance beforehand beats
                discovering it through a failed search. */}
            {health?.provider_quota_remaining != null && (
              <span
                title={
                  health.provider_quota_remaining === 0
                    ? t("header.quotaEmptyHint")
                    : t("header.quotaHint", { count: health.provider_quota_remaining })
                }
                className={`px-2 py-1 rounded-full ring-1 tabular-nums ${
                  health.provider_quota_remaining === 0
                    ? "bg-danger-soft text-danger ring-danger-line"
                    : health.provider_quota_remaining <= 25
                      ? "bg-warning-soft text-warning ring-warning-line"
                      : "bg-surface-2 text-ink-muted ring-line-strong"
                }`}
              >
                {health.provider_quota_remaining === 0
                  ? t("header.quotaEmpty")
                  : t("header.quota", { count: health.provider_quota_remaining })}
              </span>
            )}

            <ThemeToggle theme={theme} onToggle={toggleTheme} />
            <LanguageToggle />
          </div>
        </div>

        <nav className="mx-auto max-w-6xl px-4 flex gap-1 text-sm">
          {navItems.map((item) => (
            <button
              key={item.key}
              type="button"
              disabled={item.disabled}
              onClick={() => navigate(item.key)}
              aria-current={route === item.key ? "page" : undefined}
              className={`px-3 py-2 -mb-px border-b-2 transition disabled:opacity-40
                          disabled:cursor-not-allowed ${
                            route === item.key
                              ? "border-accent text-ink font-semibold"
                              : "border-transparent text-ink-muted hover:text-ink"
                          }`}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6 space-y-6">
        {route === "search" && (
          <>
            <SearchForm busy={busy} onSearch={runSearch} />
            <p className="text-sm text-ink-faint max-w-2xl">{t("empty.intro")}</p>
          </>
        )}

        {route === "results" && (
          <>
            {error && (
              <div className="rounded-xl border border-danger-line bg-danger-soft text-danger px-4 py-3">
                {error}
              </div>
            )}

            {busy && <BatchProgress events={events} />}

            {result && !busy && (
              <ResultsPanel
                result={result}
                disclaimerAccepted={accepted}
                onOpenDisclaimer={() => navigate("rules")}
              />
            )}

            {(result || error) && !busy && (
              <div className="flex flex-wrap gap-3">
                {error && (
                  <button
                    type="button"
                    onClick={retrySearch}
                    className="rounded-lg bg-accent hover:bg-accent-hover px-5 py-2.5 text-sm
                               font-semibold text-accent-ink transition"
                  >
                    {t("nav.searchAgain")}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => navigate("search")}
                  className="rounded-lg ring-1 ring-line-strong px-5 py-2.5 text-sm font-semibold
                             text-ink-muted hover:text-ink transition"
                >
                  {error ? t("nav.changeSearch") : t("nav.newSearch")}
                </button>
              </div>
            )}
          </>
        )}

        {route === "rules" && (
          <RulesPage
            disclaimer={disclaimer}
            accepted={accepted}
            onAccept={() => {
              accept(result?.search_id ?? null);
              // Straight back to what they were trying to see.
              if (result) navigate("results");
            }}
            onBack={() => navigate(result ? "results" : "search")}
          />
        )}
      </main>

      {/* The modal remains the hard gate; the page is for reading properly. */}
      {open && disclaimer && (
        <DisclaimerModal
          disclaimer={disclaimer}
          onAccept={() => accept(result?.search_id ?? null)}
          onDismiss={() => setOpen(false)}
        />
      )}
    </div>
  );
}
