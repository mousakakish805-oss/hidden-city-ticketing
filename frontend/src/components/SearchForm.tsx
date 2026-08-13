import { useEffect, useState } from "react";

import { useI18n } from "../i18n";
import { addDays, dateInDays } from "../lib/format";
import type { Cabin, SearchParams } from "../types";
import { AirportInput } from "./AirportInput";

const CABINS: Cabin[] = ["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"];

interface Props {
  busy: boolean;
  onSearch: (params: SearchParams) => void;
}

export function SearchForm({ busy, onSearch }: Props) {
  const { t, lang } = useI18n();
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
      className="rounded-2xl bg-surface ring-1 ring-line p-5 backdrop-blur"
    >
      <div
        role="group"
        aria-label={t("form.tripType")}
        className="mb-4 inline-flex rounded-lg ring-1 ring-line-strong overflow-hidden text-sm"
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
                ? "bg-ink text-canvas font-semibold"
                : "text-ink-muted hover:text-ink"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div
        className={`grid gap-4 ${
          isRoundTrip
            ? "md:grid-cols-[1fr_1fr_1fr_1fr_auto]"
            : "md:grid-cols-[1fr_1fr_1fr_auto]"
        }`}
      >
        <AirportInput
          label={t("form.from")}
          value={params.origin}
          placeholder="AMM"
          onChange={(origin) => patch({ origin })}
        />
        <AirportInput
          label={t("form.to")}
          hint={t("form.toHint")}
          value={params.destination}
          placeholder="IST"
          onChange={(destination) => patch({ destination })}
        />
        <div>
          <label
            htmlFor="departure"
            className="block text-xs font-medium uppercase tracking-wider text-ink-faint mb-1.5"
          >
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
            className="w-full rounded-lg bg-surface ring-1 ring-line px-3 py-2.5 text-base
                       focus:outline-none focus:ring-2 focus:ring-accent"
          />
        </div>

        {isRoundTrip && (
          <div>
            <label
              htmlFor="return"
              className="block text-xs font-medium uppercase tracking-wider text-ink-faint mb-1.5"
            >
              {t("form.returnDate")}
            </label>
            <input
              id="return"
              type="date"
              value={params.return_date ?? ""}
              min={params.departure_date}
              max={dateInDays(360)}
              onChange={(event) => patch({ return_date: event.target.value || null })}
              className="w-full rounded-lg bg-surface ring-1 ring-line px-3 py-2.5 text-base
                         focus:outline-none focus:ring-2 focus:ring-accent"
            />
          </div>
        )}
        <div className="flex items-end">
          <button
            type="submit"
            disabled={busy || invalid}
            className="w-full md:w-auto rounded-lg bg-accent hover:bg-accent-hover disabled:bg-surface-2
                       disabled:text-ink-faint px-6 py-2.5 font-semibold text-accent-ink transition"
          >
            {busy ? t("form.searching") : t("form.search")}
          </button>
        </div>
      </div>

      {sameAirports && <p className="mt-3 text-sm text-danger">{t("form.sameAirports")}</p>}
      {returnTooEarly && (
        <p className="mt-3 text-sm text-danger">{t("form.returnBeforeDeparture")}</p>
      )}
      {isRoundTrip && !returnTooEarly && (
        <p className="mt-3 text-xs text-ink-faint max-w-2xl">{t("form.twoTicketsNote")}</p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-ink-muted">
        <label className="flex items-center gap-2">
          <span>{t("form.passengers")}</span>
          <input
            type="number"
            min={1}
            max={9}
            value={params.adults}
            onChange={(event) => patch({ adults: Number(event.target.value) })}
            className="w-16 rounded bg-surface ring-1 ring-line px-2 py-1"
          />
        </label>

        <label className="flex items-center gap-2">
          <span>{t("form.cabin")}</span>
          <select
            value={params.cabin}
            onChange={(event) => patch({ cabin: event.target.value as Cabin })}
            className="rounded bg-surface ring-1 ring-line px-2 py-1"
          >
            {CABINS.map((cabin) => (
              <option key={cabin} value={cabin}>
                {t(`cabin.${cabin}` as "cabin.ECONOMY")}
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
