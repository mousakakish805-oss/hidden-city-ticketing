import { duration, plural, useI18n } from "../i18n";
import { money, timeOfDay } from "../lib/format";
import type { Offer } from "../types";
import { SegmentTimeline } from "./SegmentTimeline";

interface Props {
  offer: Offer;
  currency: string;
  isCheapest: boolean;
}

/** An ordinary A -> B result: what any other flight search would show. */
export function StandardOfferCard({ offer, currency, isCheapest }: Props) {
  const { t, locale } = useI18n();
  const itinerary = offer.itineraries[0];
  if (!itinerary) return null;

  const first = itinerary.segments[0];
  const last = itinerary.segments[itinerary.segments.length - 1];

  return (
    <div
      className={`rounded-xl bg-surface ring-1 p-4 ${
        isCheapest ? "ring-accent-line" : "ring-line"
      }`}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <SegmentTimeline itinerary={itinerary} />
          <p className="mt-1.5 text-xs text-ink-faint">
            {offer.primary_carrier_name} &middot; {duration(t, itinerary.duration_minutes)}{" "}
            &middot;{" "}
            {offer.stop_count === 0
              ? t("standard.nonstop")
              : plural(t, "standard.stops", offer.stop_count)}
            {first && last && (
              <>
                {" "}
                &middot;{" "}
                <span dir="ltr">
                  {timeOfDay(first.departure_at, locale)} – {timeOfDay(last.arrival_at, locale)}
                </span>
              </>
            )}
          </p>
        </div>
        <div className="text-end shrink-0">
          <p className="text-xl font-bold">{money(offer.price_total, currency, locale)}</p>
          {isCheapest && <p className="text-xs text-accent font-medium">{t("standard.cheapest")}</p>}
        </div>
      </div>
    </div>
  );
}
