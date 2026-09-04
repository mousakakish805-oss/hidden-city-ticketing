import { useEffect, useMemo, useState } from "react";

import { useI18n } from "../i18n";
import { currencyOptions } from "../lib/currencies";
import { addDays, dateInDays } from "../lib/format";
import type { Cabin, SearchParams } from "../types";
import { AirportInput } from "./AirportInput";

const CABINS: Cabin[] = ["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"];

const FIELD =
  "w-full rounded bg-canvas border border-line px-3 py-2.5 text-base transition " +
  "focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent";

const LABEL = "block text-xs font-medium text-ink-muted mb-1.5";

interface Props {
  busy: boolean;
  onSearch: (params: SearchParams) => void;
}

export function SearchForm({ busy, onSearch }: Props) {
  const { t, lang, locale } = useI18n();
  const [params, setParams] = useState<SearchParams>({
    origin: "AMM",
    destination: "IST",
    departure_date: dateInDays(45),
    return_date: null,
    adults: 1,
    cabin: "ECONOMY",
    currency: "USD",
    include_nearby_airports: false,
    refresh: false,
    lang,
  });

  const currencies = useMemo(() => currencyOptions(locale), [locale]);

  const isRoundTrip = params.return_date !== null;

  const setTripType = (roundTrip: boolean) =>
    setParams((previous) => ({
      ...previous,
      // Default the return a week out, which is what most people want.
      return_date: roundTrip
        ? (previous.return_date ?? addDays(previous.departure_date, 7))
        : null,
    }));

  // Results are rendered server-side in the requested language, so the next
  // search must carry whatever is currently selected.
  useEffect(() => {
    setParams((previous) => ({ ...previous, lang }));
  }, [lang]);

  const patch = (changes: Partial<SearchParams>) =>
    setParams((previous) => ({ ...previous, ...changes }));

  const swapAirports = () =>
    setParams((previous) => ({
      ...previous,
      origin: previous.destination,
      destination: previous.origin,
    }));

  const sameAirports = params.origin === params.destination && params.origin.length === 3;
  const returnTooEarly =
    params.return_date !== null && params.return_date < params.departure_date;
  const invalid =
    params.origin.length !== 3 ||
    params.destination.length !== 3 ||
    sameAirports ||
    returnTooEarly;

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (!invalid) onSearch(params);
      }}
      className="ticket flex flex-col lg:flex-row shadow-[var(--shadow)]"
    >
      <div className="flex-1 p-5 sm:p-6 min-w-0">
      <div
        role="group"
        aria-label={t("form.tripType")}
        className="mb-5 inline-flex border border-line rounded overflow-hidden text-sm"
      >
        {[
          { round: false, label: t("form.oneWay") },
          { round: true, label: t("form.roundTrip") },
        ].map((option) => (
          <button
            key={option.label}
            type="button"
            onClick={() => setTripType(option.round)}
            aria-pressed={isRoundTrip === option.round}
            className={`px-4 py-1.5 transition ${
              isRoundTrip === option.round
                ? "bg-accent text-accent-ink font-semibold"
                : "text-ink-muted hover:text-ink"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div
        className={`grid gap-4 items-end ${
          isRoundTrip
            ? "lg:grid-cols-[1fr_auto_1fr_1fr_1fr_auto]"
            : "lg:grid-cols-[1fr_auto_1fr_1fr_auto]"
        }`}
      >
        <AirportInput
          label={t("form.from")}
          value={params.origin}
          placeholder="AMM"
          onChange={(origin) => patch({ origin })}
        />

        {/* Reverses the route in place. The commonest edit to a flight search
            is the one that needs no typing at all. */}
        <button
          type="button"
          onClick={swapAirports}
          title={t("form.swap")}
          aria-label={t("form.swap")}
          className="hidden lg:flex h-11 w-11 shrink-0 items-center justify-center self-end
                     rounded-full ring-1 ring-line-strong text-ink-muted transition
                     hover:text-accent hover:ring-accent hover:rotate-180 active:scale-90"
        >
          <span aria-hidden className="text-lg leading-none">
            ⇄
          </span>
        </button>

        <AirportInput
          label={t("form.to")}
          hint={t("form.toHint")}
          value={params.destination}
          placeholder="IST"
          onChange={(destination) => patch({ destination })}
        />

        <div>
          <label htmlFor="departure" className={LABEL}>
            {t("form.departure")}
          </label>
          <input
            id="departure"
            type="date"
            value={params.departure_date}
            min={dateInDays(0)}
            max={dateInDays(360)}
            onChange={(event) => {
              const departure = event.target.value;
              // Drag the return along rather than leaving it in the past.
              patch({
                departure_date: departure,
                ...(params.return_date && params.return_date < departure
                  ? { return_date: departure }
                  : {}),
              });
            }}
            className={FIELD}
          />
        </div>

        {isRoundTrip && (
          <div className="">
            <label htmlFor="return" className={LABEL}>
              {t("form.returnDate")}
            </label>
            <input
              id="return"
              type="date"
              value={params.return_date ?? ""}
              min={params.departure_date}
              max={dateInDays(360)}
              onChange={(event) => patch({ return_date: event.target.value || null })}
              className={FIELD}
            />
          </div>
        )}

        <button
          type="submit"
          disabled={busy || invalid}
          className="rounded-xl bg-accent hover:bg-accent-hover disabled:bg-surface-2
                     disabled:text-ink-faint disabled:cursor-not-allowed px-7 py-3
                     font-semibold text-accent-ink transition disabled:hover:translate-y-0 disabled:hover:shadow-none"
        >
          {busy ? (
            <span className="inline-flex items-center gap-2">
              <span
                aria-hidden
                className="h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent
                           animate-spin"
              />
              {t("form.searching")}
            </span>
          ) : (
            t("form.search")
          )}
        </button>
      </div>

      {sameAirports && <p className="mt-3 text-sm text-danger">{t("form.sameAirports")}</p>}
      {returnTooEarly && (
        <p className="mt-3 text-sm text-danger">{t("form.returnBeforeDeparture")}</p>
      )}
      {isRoundTrip && !returnTooEarly && (
        <p className="mt-3 text-xs text-ink-faint max-w-2xl">{t("form.twoTicketsNote")}</p>
      )}

      </div>

      

      <div
        className="p-5 sm:p-6 flex flex-row flex-wrap lg:flex-col gap-x-6 gap-y-4
                   border-t border-dashed border-line-strong lg:border-t-0 lg:border-s
                   text-sm text-ink-muted lg:w-56 shrink-0"
      >
        <label className="flex items-center gap-2">
          <span>{t("form.passengers")}</span>
          <input
            type="number"
            min={1}
            max={9}
            value={params.adults}
            onChange={(event) => patch({ adults: Number(event.target.value) })}
            className="w-16 rounded-lg bg-canvas ring-1 ring-line px-2 py-1.5 tabular-nums"
          />
        </label>

        <label className="flex items-center gap-2">
          <span>{t("form.cabin")}</span>
          <select
            value={params.cabin}
            onChange={(event) => patch({ cabin: event.target.value as Cabin })}
            className="rounded-lg bg-canvas ring-1 ring-line px-2 py-1.5"
          >
            {CABINS.map((cabin) => (
              <option key={cabin} value={cabin}>
                {t(`cabin.${cabin}` as "cabin.ECONOMY")}
              </option>
            ))}
          </select>
        </label>

        {/* Passed straight through to the provider, so fares are quoted in
            this currency rather than converted after the fact -- a converted
            price would drift from what the airline actually charges. */}
        <label className="flex items-center gap-2">
          <span>{t("form.currency")}</span>
          <select
            value={params.currency}
            onChange={(event) => patch({ currency: event.target.value })}
            className="rounded-lg bg-canvas ring-1 ring-line px-2 py-1.5 max-w-[13rem]"
          >
            {currencies.map((option) => (
              <option key={option.code} value={option.code}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-2 cursor-pointer" title={t("form.nearbyHint")}>
          <input
            type="checkbox"
            checked={params.include_nearby_airports}
            onChange={(event) => patch({ include_nearby_airports: event.target.checked })}
            className="accent-[var(--accent)]"
          />
          <span>{t("form.nearby")}</span>
        </label>

        <label className="flex items-center gap-2 cursor-pointer" title={t("form.bypassCacheHint")}>
          <input
            type="checkbox"
            checked={params.refresh}
            onChange={(event) => patch({ refresh: event.target.checked })}
            className="accent-[var(--accent)]"
          />
          <span>{t("form.bypassCache")}</span>
        </label>
      </div>
    </form>
  );
}
