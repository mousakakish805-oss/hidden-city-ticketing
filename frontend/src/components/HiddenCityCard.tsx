import { useState } from "react";

import { duration, useI18n } from "../i18n";
import { money, SEVERITY_CLASS, shortDate, timeOfDay } from "../lib/format";
import type { HiddenCityOption } from "../types";
import { BookingPanel } from "./BookingPanel";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { SegmentTimeline } from "./SegmentTimeline";

interface Props {
  option: HiddenCityOption;
  currency: string;
}

/**
 * The headline result: what to book, where to get off, and what it costs you
 * in risk to save the money.
 */
export function HiddenCityCard({ option, currency }: Props) {
  const { t, locale } = useI18n();
  const [showAllFlags, setShowAllFlags] = useState(false);
  const itinerary = option.offer.itineraries[0];
  if (!itinerary) return null;

  const flown = itinerary.segments.slice(0, option.deplane_index + 1);
  const skipped = itinerary.segments.slice(option.deplane_index + 1);
  const critical = option.risk.flags.filter((flag) => flag.severity === "critical");
  const visibleFlags = showAllFlags ? option.risk.flags : critical;

  return (
    <article
      className="rounded-2xl bg-gradient-to-b from-positive-soft to-transparent
                 ring-1 ring-positive-line p-5 animate-fade-up"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wider text-positive font-semibold mb-1">
            {t("card.badge")}
          </p>
          <h3 className="text-lg font-bold">
            {t("card.bookTo", { city: option.ticketed_city })}
            <span className="font-mono text-ink-muted" dir="ltr">
              {" "}
              ({option.ticketed_iata})
            </span>
          </h3>
          <p className="text-sm text-ink-muted mt-0.5">
            <span className="text-positive font-semibold">
              {t("card.getOffAt", { city: option.deplane_city })}{" "}
              <span dir="ltr">({option.deplane_iata})</span>
            </span>{" "}
            &mdash; {t("card.yourDestination")}
            {option.is_nearby_airport && (
              <span className="ms-2 text-warning text-xs">{t("card.nearbyWarning")}</span>
            )}
          </p>
        </div>

        <div className="text-end">
          <p className="text-3xl font-bold text-positive">
            {money(option.price, currency, locale)}
          </p>
          <p className="text-sm text-ink-faint line-through">
            {money(option.baseline_price, currency, locale)}
          </p>
          <p className="text-sm font-semibold text-positive mt-0.5">
            {t("card.save", {
              amount: money(option.savings, currency, locale),
              percent: option.savings_percent,
            })}
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <SegmentTimeline itinerary={itinerary} deplaneIata={option.deplane_iata} />
        <ConfidenceBadge risk={option.risk} />
      </div>

      {/* Airport codes and times are identifiers -- always left-to-right. */}
      <div
        dir="ltr"
        className="mt-4 rounded-xl bg-surface-2 ring-1 ring-line divide-y divide-line"
      >
        {flown.map((segment, index) => (
          <div key={`flown-${index}`} className="flex items-center gap-3 px-3 py-2 text-sm">
            <span
              className="font-mono text-xs text-ink-faint w-16 shrink-0"
              title={segment.carrier_name}
            >
              {segment.carrier} {segment.flight_number}
            </span>
            <span className="font-mono">{segment.origin}</span>
            <span className="text-ink-faint">{timeOfDay(segment.departure_at, locale)}</span>
            <span className="text-ink-faint" aria-hidden="true">
              &#8594;
            </span>
            <span className="font-mono">{segment.destination}</span>
            <span className="text-ink-faint">{timeOfDay(segment.arrival_at, locale)}</span>
            <span className="ms-auto text-xs text-ink-faint">
              {duration(t, segment.duration_minutes)}
            </span>
          </div>
        ))}

        {skipped.map((segment, index) => (
          <div
            key={`skipped-${index}`}
            className="flex items-center gap-3 px-3 py-2 text-sm text-ink-faint"
          >
            <span className="font-mono text-xs w-16 shrink-0" title={segment.carrier_name}>
              {segment.carrier} {segment.flight_number}
            </span>
            <span className="font-mono line-through">{segment.origin}</span>
            <span className="text-ink-faint" aria-hidden="true">
              &#8594;
            </span>
            <span className="font-mono line-through">{segment.destination}</span>
            <span className="ms-auto text-xs uppercase tracking-wider text-danger">
              {t("card.youSkip")}
            </span>
          </div>
        ))}
      </div>

      <dl className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <div>
          <dt className="text-ink-faint text-xs">{t("card.travelTime")}</dt>
          <dd className="font-semibold">{duration(t, option.usable_duration_minutes)}</dd>
        </div>
        <div>
          <dt className="text-ink-faint text-xs">{t("card.arrive")}</dt>
          <dd className="font-semibold">
            {shortDate(option.usable_arrival, locale)} {timeOfDay(option.usable_arrival, locale)}
          </dd>
        </div>
        <div>
          <dt className="text-ink-faint text-xs">{t("card.airline")}</dt>
          <dd className="font-semibold">{option.booking.carrier_name}</dd>
        </div>
        <div>
          <dt className="text-ink-faint text-xs">{t("card.groundTime")}</dt>
          <dd className="font-semibold">
            {duration(t, option.layover_minutes)}
          </dd>
        </div>
      </dl>

      <BookingPanel booking={option.booking} />

      <div className="mt-4 space-y-2">
        {visibleFlags.map((flag) => (
          <div
            key={flag.code}
            className={`rounded-lg border px-3 py-2 text-sm ${SEVERITY_CLASS[flag.severity] ?? ""}`}
          >
            {flag.message}
          </div>
        ))}
        <button
          type="button"
          onClick={() => setShowAllFlags((previous) => !previous)}
          className="text-xs text-ink-faint hover:text-ink-muted underline underline-offset-2"
        >
          {showAllFlags
            ? t("card.showCritical")
            : t("card.showAll", { count: option.risk.flags.length })}
        </button>
      </div>
    </article>
  );
}
