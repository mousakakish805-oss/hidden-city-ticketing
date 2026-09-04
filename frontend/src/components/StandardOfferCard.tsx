import { duration, plural, useI18n } from "../i18n";
import { googleFlightsUrl } from "../lib/booking";
import { money, shortDate, timeOfDay } from "../lib/format";
import type { Offer } from "../types";
import { SegmentTimeline } from "./SegmentTimeline";

interface Props {
  offer: Offer;
  currency: string;
  isCheapest: boolean;
  /** Departure date, so the booking search opens on the right day. */
  departureDate: string;
}

/**
 * An ordinary A -> B fare: what any other flight search would show.
 *
 * Built to the same pattern as the hidden-city card — header and price, the
 * legs with their flight numbers and times, a row of the four facts that
 * decide between two fares, then somewhere to book. These are the whole
 * answer whenever no anomaly is found, which is the common case, and a fare
 * a traveller might actually take should not be a thinner thing on the page
 * than one they probably should not.
 *
 * Deliberately quieter than the green card: no gradient, no confidence score,
 * no warnings. Nothing here needs warning about, and the hidden-city result
 * has to stay the one that catches the eye.
 */
export function StandardOfferCard({ offer, currency, isCheapest, departureDate }: Props) {
  const { t, locale } = useI18n();
  const itinerary = offer.itineraries[0];
  if (!itinerary) return null;

  const first = itinerary.segments[0];
  const last = itinerary.segments[itinerary.segments.length - 1];

  return (
    <article
      className={`rounded-2xl bg-surface border p-5 ${
        isCheapest ? "border-accent-line" : "border-line"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold text-ink-faint mb-1.5">
            {offer.stop_count === 0
              ? t("standard.nonstop")
              : plural(t, "standard.stops", offer.stop_count)}
          </p>
          <SegmentTimeline itinerary={itinerary} />
        </div>

        <div className="text-end shrink-0">
          <p className="text-2xl font-bold">{money(offer.price_total, currency, locale)}</p>
          {isCheapest && (
            <p className="text-sm font-semibold text-accent mt-0.5">{t("standard.cheapest")}</p>
          )}
        </div>
      </div>

      {/* Airport codes, flight numbers and times are identifiers -- always
          left-to-right, whatever the page language. */}
      <div
        dir="ltr"
        className="mt-4 rounded-xl bg-surface-2 border border-line divide-y divide-line"
      >
        {itinerary.segments.map((segment, index) => (
          <div key={index} className="flex items-center gap-3 px-3 py-2 text-sm">
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
      </div>

      <dl className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <div>
          <dt className="text-ink-faint text-xs">{t("card.travelTime")}</dt>
          <dd className="font-semibold">{duration(t, itinerary.duration_minutes)}</dd>
        </div>
        <div>
          <dt className="text-ink-faint text-xs">{t("standard.departs")}</dt>
          <dd className="font-semibold">{first && timeOfDay(first.departure_at, locale)}</dd>
        </div>
        <div>
          <dt className="text-ink-faint text-xs">{t("card.arrive")}</dt>
          <dd className="font-semibold">
            {last && (
              <>
                {shortDate(last.arrival_at, locale)} {timeOfDay(last.arrival_at, locale)}
              </>
            )}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-ink-faint text-xs">{t("card.airline")}</dt>
          <dd className="font-semibold truncate">{offer.primary_carrier_name}</dd>
        </div>
      </dl>

      <div className="mt-4 rounded-xl bg-surface-2 border border-line p-4">
        <p className="text-xs font-semibold text-ink-faint mb-1">{t("booking.title")}</p>
        <p className="text-sm text-ink-muted">
          {t("standard.bookInstructions", {
            origin: offer.search_origin,
            destination: offer.search_destination,
            date: departureDate,
          })}
        </p>
        <a
          href={googleFlightsUrl(offer.search_origin, offer.search_destination, departureDate)}
          target="_blank"
          // noreferrer alongside noopener: the destination should not receive
          // this tool as the referrer.
          rel="noopener noreferrer"
          className="mt-3 inline-block rounded bg-accent hover:bg-accent-hover px-4 py-2 text-sm
                     font-semibold text-accent-ink transition"
        >
          {t("standard.seeOnGoogle")}
        </a>
        <p className="text-xs text-ink-faint mt-2">{t("booking.note")}</p>
      </div>
    </article>
  );
}
