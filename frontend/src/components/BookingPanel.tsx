import { useI18n } from "../i18n";
import type { BookingGuidance } from "../types";

/**
 * Where to buy the fare.
 *
 * Two links, because they fail in different ways. The first opens Google
 * Flights on the ticketed one-way market, so the itinerary is on screen rather
 * than described in a sentence someone has to retype into another site. The
 * second is the airline's own homepage — deliberately the homepage, since
 * every carrier's booking-flow URL differs and those formats change without
 * notice, so a fabricated deep link breaks quietly. Between them, one of the
 * two always works.
 *
 * This website never books anything; it only reports prices.
 */
export function BookingPanel({ booking }: { booking: BookingGuidance }) {
  const { t } = useI18n();

  return (
    <div className="mt-4 rounded bg-surface-2 border border-line p-4">
      <p className="text-xs font-semibold text-ink-faint mb-1">{t("booking.title")}</p>
      <p className="text-sm text-ink-muted">{booking.instructions}</p>
      {booking.note && <p className="text-sm text-warning mt-1">{booking.note}</p>}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <a
          href={booking.search_url}
          target="_blank"
          // noreferrer alongside noopener: the destination should not receive
          // this tool as the referrer.
          rel="noopener noreferrer"
          className="rounded bg-accent hover:bg-accent-hover px-4 py-2 text-sm font-semibold
                     text-accent-ink transition"
        >
          {booking.search_label}
        </a>

        {booking.url && (
          <a
            href={booking.url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded border border-line-strong px-4 py-2 text-sm font-semibold
                       text-ink-muted hover:text-ink transition"
          >
            {t("booking.openSite", { airline: booking.carrier_name })}
          </a>
        )}
      </div>

      <p className="text-xs text-ink-faint mt-2.5">{booking.search_note}</p>
      <p className="text-xs text-ink-faint mt-1">{t("booking.note")}</p>
    </div>
  );
}
