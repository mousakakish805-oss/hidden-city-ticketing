import { duration, plural, useI18n } from "../i18n";
import { googleFlightsUrl } from "../lib/booking";
import { money, timeOfDay } from "../lib/format";
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
 * An ordinary A -> B result: what any other flight search would show.
 *
 * It carries a booking link for the same reason the hidden-city cards do.
 * When no anomaly is found -- the common case, and the honest one -- this
 * list is the whole answer, and a page of prices with nothing to act on
 * leaves the reader retyping the route into another site by hand.
 */
export function StandardOfferCard({ offer, currency, isCheapest, departureDate }: Props) {
  const { t, locale } = useI18n();
  const itinerary = offer.itineraries[0];
  if (!itinerary) return null;

  const first = itinerary.segments[0];
  const last = itinerary.segments[itinerary.segments.length - 1];

  return (
    <div
      className={`rounded-xl bg-surface border p-4 ${
        isCheapest ? "border-accent-line" : "border-line"
      }`}
    >
      {/* One row, one column per fact. Stacking the route over a meta line
          and pushing the price to the far edge left 657px of nothing in the
          middle of a 1120px card -- and capping the width instead only made
          these the one element on the page that did not line up. */}
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 text-xs text-ink-faint">
        <div className="min-w-0 shrink-0">
          <SegmentTimeline itinerary={itinerary} />
        </div>

        {/* Each field is isolated. Concatenated into one Arabic string they
            reordered across each other, and "2h 15m" came apart. */}
        <bdi className="truncate max-w-[12rem]">{offer.primary_carrier_name}</bdi>
        <bdi>{duration(t, itinerary.duration_minutes)}</bdi>
        <bdi>
          {offer.stop_count === 0
            ? t("standard.nonstop")
            : plural(t, "standard.stops", offer.stop_count)}
        </bdi>
        {first && last && (
          <bdi dir="ltr">
            {timeOfDay(first.departure_at, locale)} – {timeOfDay(last.arrival_at, locale)}
          </bdi>
        )}

        <div className="flex items-center gap-4 shrink-0">
          <div className="text-end">
            <p className="text-xl font-bold text-ink">
              {money(offer.price_total, currency, locale)}
            </p>
            {isCheapest && (
              <p className="text-xs text-accent font-medium">{t("standard.cheapest")}</p>
            )}
          </div>
          <a
            href={googleFlightsUrl(offer.search_origin, offer.search_destination, departureDate)}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded border border-line-strong px-3 py-1.5 text-xs font-semibold
                       text-ink-muted hover:text-ink hover:border-accent transition"
          >
            {t("standard.book")}
          </a>
        </div>
      </div>
    </div>
  );
}
