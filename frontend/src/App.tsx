import { useCallback, useEffect, useRef, useState } from "react";

import { BatchProgress } from "./components/BatchProgress";
import { DisclaimerModal } from "./components/DisclaimerModal";
import { HeroTicket } from "./components/HeroTicket";
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

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-20">
        <div className="mx-auto max-w-6xl px-4 py-3 flex items-center gap-3
                        bg-canvas border-b border-line">
          <button
            type="button"
            onClick={() => navigate("search")}
            className="min-w-0 text-start group"
          >
            <h1 className="text-base font-bold tracking-tight flex items-center gap-2">
              <span
                aria-hidden
                className="inline-block h-2 w-2 rounded-full bg-accent
                           transition-transform group-hover:scale-150"
              />
              {t("app.title")}
            </h1>
            <p className="text-[11px] text-ink-faint truncate">{t("app.subtitle")}</p>
          </button>

          <div className="ms-auto flex items-center gap-2 text-xs shrink-0">
            {health && (
              <span
                title={
                  health.provider_live
                    ? t("header.liveHint", { provider: health.provider })
                    : t("header.syntheticHint")
                }
                className={`hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full ring-1 ${
                  health.provider_live
                    ? "bg-positive-soft text-positive ring-positive-line"
                    : "bg-warning-soft text-warning ring-warning-line"
                }`}
              >
                {health.provider_live && (
                  <span aria-hidden className="relative flex h-1.5 w-1.5">
                    <span className="absolute inset-0 rounded-full bg-positive " />
                    <span className="relative h-1.5 w-1.5 rounded-full bg-positive" />
                  </span>
                )}
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
                className={`hidden sm:inline px-2.5 py-1 rounded-full ring-1 tabular-nums ${
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
      </header>

      <main className="flex-1 mx-auto w-full max-w-6xl px-4 pb-16">
        {route === "search" && (
          <section key="landing" className="pt-10 sm:pt-14">
            {/* The claim in words, and the same claim as an object. The ticket
                is the only loud thing on this page; everything below it is
                deliberately quiet. */}
            <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
              <div className="max-w-xl">
                <h2 className="text-4xl sm:text-5xl font-semibold tracking-tight leading-[1.08]">
                  {t("hero.title")}
                </h2>
                <p className="mt-5 text-base text-ink-muted leading-relaxed max-w-prose">
                  {t("hero.body")}
                </p>
              </div>
              <HeroTicket />
            </div>

            <div className="mt-12">
              <SearchForm busy={busy} onSearch={runSearch} />
              {/* Directly under the form. These rules are what separates a
                  saving from a voided ticket, so they belong where someone
                  is about to search -- not in the header furniture, and not
                  only on a results page they may never reach. */}
              <div className="mt-4 flex flex-wrap items-baseline gap-x-4 gap-y-2">
                <button
                  type="button"
                  onClick={() => navigate("rules")}
                  className="text-sm font-semibold text-accent underline underline-offset-4
                             decoration-accent-line hover:decoration-accent transition"
                >
                  {t("header.rules")}
                </button>
                {coverage && (
                  <p className="text-xs text-ink-faint">
                    {t("app.coverage", {
                      airports: number(coverage.airports, locale),
                      countries: number(coverage.countries, locale),
                    })}
                  </p>
                )}
              </div>
            </div>

            {/* Genuinely a sequence, so it is numbered; set as three lines of
                prose rather than three identical cards, because the content is
                a sentence each and cards would be packaging around nothing. */}
            <ol className="mt-12 grid gap-6 sm:grid-cols-3 max-w-4xl">
              {(["one", "two", "three"] as const).map((step, index) => (
                <li key={step}>
                  <p className="coupon text-xs text-accent">{number(index + 1, locale)}</p>
                  <p className="mt-1.5 font-semibold text-sm">{t(`how.${step}.title`)}</p>
                  <p className="mt-1 text-sm text-ink-muted leading-relaxed">
                    {t(`how.${step}.body`)}
                  </p>
                </li>
              ))}
            </ol>
          </section>
        )}

        {route === "results" && (
          <div key="results" className="pt-6 space-y-6">
            {error && (
              <div
                role="alert"
                className="rounded-2xl border border-danger-line bg-danger-soft text-danger px-4 py-3"
              >
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
                    className="rounded-xl bg-accent hover:bg-accent-hover px-5 py-2.5 text-sm
                               font-semibold text-accent-ink transition "
                  >
                    {t("nav.searchAgain")}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => navigate("search")}
                  className="rounded-xl ring-1 ring-line-strong px-5 py-2.5 text-sm font-semibold
                             text-ink-muted hover:text-ink transition "
                >
                  {error ? t("nav.changeSearch") : t("nav.newSearch")}
                </button>
              </div>
            )}
          </div>
        )}

        {route === "rules" && (
          <div key="rules" className="pt-6">
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
          </div>
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
